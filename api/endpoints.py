from fastapi import APIRouter, UploadFile, File, Form, HTTPException,Depends
import shutil
from fastapi.responses import JSONResponse
import os
from fastapi import HTTPException
import logging
from services.summary import stream_summary
logger = logging.getLogger(__name__)
from fastapi.responses import StreamingResponse
from services.mcqs import MCQGeneratorGemini,MCQGeneratorMistral, MCQGeneratorChatGPT
from pydantic import BaseModel
from typing import List
router = APIRouter()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
from core.config import OPENAI_API_KEY
from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)
import json
from services.report import process_pdf
from datastorage.db_connect import save_student_report
import re
from services.auth import hash_password, verify_password, create_access_token, decode_access_token, get_user_by_username
from datetime import timedelta
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from bson import ObjectId
from fastapi import APIRouter, Form, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import timedelta
from datastorage.db_connect import users_collection, reports_collection
from services.auth import hash_password, verify_password, create_access_token, decode_access_token,get_user_by_username
from core.prompts import MCQ_PROMPT_WITH_REPORT,MCQ_PROMPT_WITHOUT_REPORT,FLASHCARD_PROMPT,FLASHCARD_PROMPT_WITH_REPORT
from services.flashcards import FlashcardGeneratorChatGPT,FlashcardGeneratorMistral,FlashcardGeneratorGemini
from services.chat import DocumentChatServiceGemini,DocumentChatServiceOpenAI
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
CHAT_SERVICES = {
    "gemini": DocumentChatServiceGemini(collection_name="document-chat-collection-gemini"),
    "chatgpt": DocumentChatServiceOpenAI(collection_name="document-chat-collection-openai")
}
async def get_user_by_username(username: str):
    """Helper function to get user from MongoDB by username."""
    user = users_collection.find_one({"username": username})
    if user:
        user['id'] = str(user['_id'])
        del user['_id']
        return user
    return None

@router.post("/register/")
async def register(username: str = Form(...), password: str = Form(...)):
    """Registers a new user and stores it in MongoDB."""
    if await get_user_by_username(username):
        raise HTTPException(status_code=400, detail="User already exists")
    
    hashed_password = hash_password(password)
    user_data = {
        "username": username,
        "password": hashed_password,
        "reports": []
    }
    
    result = users_collection.insert_one(user_data)
    return {
        "message": "User registered successfully",
        "user_id": str(result.inserted_id)
    }

@router.post("/login/")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticates user and returns a JWT token."""
    user = await get_user_by_username(form_data.username)
    
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token = create_access_token(
        data={"sub": user["id"]},
        expires_delta=timedelta(minutes=30)
    )
    return {"access_token": access_token, "token_type": "bearer"}

def close_db_connection():
    client.close()

@router.post("/notes/")
async def generate_notes(files: list[UploadFile] = File(...), model: str = Form(...)):
    """Accept multiple PDFs, process them, and return structured notes."""
    
    file_paths = []
    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        file_paths.append(file_path)
    
    return StreamingResponse(stream_summary(file_paths,model))

class TopicSelection(BaseModel):
    topics: List[str]
    file_paths: List[str]
    model: str

class MCQResponse(BaseModel):
    topic: str
    question: str
    options: List[str]
    correct_answer: str

def get_mcq_generator(model: str):
    """Returns the appropriate MCQ generator class based on the selected model."""
    model_map = {
        "gemini": MCQGeneratorGemini,
        "mistral":MCQGeneratorMistral,
        "chatgpt":MCQGeneratorChatGPT,
    }
    if model not in model_map:
        raise HTTPException(status_code=400, detail="Invalid model specified")
    return model_map[model]()

@router.post("/mcqs/")
async def extract_topics(files: List[UploadFile] = File(...), model: str = Form(...)):
    """Extracts structured topics from uploaded PDFs using the selected AI model."""
    mcq_generator = get_mcq_generator(model)
    structured_topics = {}

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    full_paths = []
    try:
        for file in files:
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            full_paths.append(file_path)
            
            extracted_topics = mcq_generator.upload_and_parse_file(file_path)
            structured_topics.update(extracted_topics)
        if not structured_topics:
            raise HTTPException(status_code=500, detail="❌ Failed to extract topics from files.")

        return {"topics": structured_topics,"file_paths": full_paths}
    finally:
        for file_path in files:
            file_path = os.path.join(UPLOAD_DIR, file_path.filename)
            if os.path.exists(file_path):
                os.remove(file_path)

@router.post("/mcqs/generate/", response_model=List[MCQResponse])
async def generate_selected_mcqs(topic_selection: TopicSelection):
    """Generates MCQs for selected topics using the uploaded file and model."""
    if not topic_selection.topics:
        raise HTTPException(status_code=400, detail="No topics selected")
    mcq_generator = get_mcq_generator(topic_selection.model.lower())
    mcqs = mcq_generator.generate_mcqs(topic_selection.topics, topic_selection.file_paths)

    if not mcqs:
        raise HTTPException(status_code=500, detail="Failed to generate MCQs")

    mcqs = mcqs.strip()
    if mcqs.startswith("```json"):
        mcqs = mcqs[7:-3]

    try:
        mcq_data = json.loads(mcqs)
    except json.JSONDecodeError as e:
        print("❌ JSON Parsing Error:", e)
        print("Raw MCQ Response:", mcqs)
        raise HTTPException(status_code=500, detail="Failed to parse MCQs")
    finally:
        for file_path in topic_selection.file_paths:
            file_path = os.path.join(UPLOAD_DIR, file_path.filename)
            if os.path.exists(file_path):
                os.remove(file_path)

    formatted_mcqs = [
        {
            "topic": mcq["Topic"],
            "question": mcq["Question"],
            "options": mcq["Options"],
            "correct_answer": mcq["Correct Answer"]
        }
        for mcq in mcq_data
    ]

    return formatted_mcqs

def extract_json(response_text):
    """Extract JSON content from Gemini API response."""
    try:
        json_match = re.search(r"```json\n(.*?)\n```", response_text, re.DOTALL)
        json_data = json_match.group(1).strip() if json_match else response_text.strip()
        return json.loads(json_data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON response from AI model")

@router.post("/report/")
async def upload_and_generate_report(file: UploadFile = File(...)):
    """Uploads a PDF, generates a report, and saves it to MongoDB if valid."""
    try:
        pdf_data = await file.read()
        student_report = process_pdf(pdf_data)
        print(student_report)
        if isinstance(student_report, dict): 
            saved_report = save_student_report(student_report)
            return {"message": "Report generated and saved successfully", "data": saved_report}
        else:
            return {"message": "Failed to generate a structured report", "data": student_report}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        file_path = os.path.join(UPLOAD_DIR, file_path.filename)
        if os.path.exists(file_path):
            os.remove(file_path)

@router.post("/report-profile/")
async def upload_and_generate_report(file: UploadFile = File(...), token: str = Depends(oauth2_scheme)):
    """Uploads a PDF, generates a report, saves it to MongoDB, and links it to the user."""
    try:
        pdf_data = await file.read()
        student_report = process_pdf(pdf_data)

        if not isinstance(student_report, dict):
            raise HTTPException(status_code=400, detail="Failed to generate a structured report")


        report_result = reports_collection.insert_one(student_report)
        doc_id = str(report_result.inserted_id)
        decoded_data = await decode_access_token(token)
        user_id = decoded_data["payload"].get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        update_result=users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"latest_report_id": doc_id}}
        )
        if update_result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        if isinstance(student_report, dict): 
            student_report["_id"] = doc_id  
            return {"message": "Report generated and saved successfully", "data": student_report}
        else:
            return {"message": "Failed to generate a structured report", "data": student_report}

    except Exception as e:
        print("❌ Error in upload_and_generate_report:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        if os.path.exists(file_path):
            os.remove(file_path)

@router.get("/profile/")
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Retrieves the logged-in user's data along with their latest report."""
    try:
        decoded_data = await decode_access_token(token)
        user_id = decoded_data["payload"].get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = users_collection.find_one({"_id":ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user_data = dict(user)
        latest_report = None

        if "latest_report_id" in user_data:
            report = reports_collection.find_one({"_id": ObjectId(user_data["latest_report_id"])})
            if report:
                latest_report = dict(report)
                latest_report["_id"] = str(latest_report["_id"])
        return {
            "username": user_data["username"],
            "latest_report": latest_report
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MCQRequest(BaseModel):
    model: str
    file_paths: List[str]

@router.post("/mcqs_normal/", response_model=List[MCQResponse])
async def generate_personalized_mcqs(
    model: str = Form(...),
    files: List[UploadFile] = File(...)
):
    try:
        prompt = MCQ_PROMPT_WITHOUT_REPORT
        mcq_generator = get_mcq_generator(model)

        full_paths = []
        for file in files:
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            full_paths.append(file_path)
        
        mcqs = mcq_generator.generate_personalized_mcqs(prompt, full_paths)
        
        if not mcqs:
            raise HTTPException(status_code=500, detail="Failed to generate MCQs")
        
        mcqs = mcqs.strip()
        json_match = re.search(r"```json\n(.*?)\n```", mcqs, re.DOTALL)
        mcq_data = json_match.group(1).strip() if json_match else mcqs.strip()

        try:
            mcq_data = json.loads(mcq_data)
        except json.JSONDecodeError as e:
            print("❌ JSON Parsing Error:", e)
            print("Raw MCQ Response:", mcqs)
            raise HTTPException(status_code=500, detail="Failed to parse MCQs")

        formatted_mcqs = [
            {
                "topic": mcq.get("Topic", "Unknown Topic"),
                "question": mcq.get("Question", "Unknown Question"),
                "options": mcq.get("Options", []),
                "correct_answer": mcq.get("Answer", "N/A")
            }
            for mcq in mcq_data if isinstance(mcq, dict)
        ]

        print(formatted_mcqs, "this is formatted")
        return formatted_mcqs

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        for file in files:
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            if os.path.exists(file_path):
                os.remove(file_path)


@router.post("/mcqs/personalized/", response_model=List[MCQResponse])
async def generate_personalized_mcqs(
    model: str = Form(...),
    files: List[UploadFile] = File(...),
    token: str = Depends(oauth2_scheme)
):
    try:
        decoded_data = await decode_access_token(token)
        user_id = decoded_data["payload"].get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user_data = dict(user)

        latest_report = None
        if "latest_report_id" in user_data:
            report = reports_collection.find_one({"_id": ObjectId(user_data["latest_report_id"])})
            if report:
                latest_report = dict(report)

        weak_areas = latest_report.get("weaknesses", []) if latest_report else []
        strong_areas = latest_report.get("strengths", []) if latest_report else []
        average_areas = latest_report.get("average",[]) if latest_report else []
        
        weak_subjects = [area["subject"] for area in weak_areas] if weak_areas else []
        strengths_formatted = ", ".join(strong_areas) if strong_areas else "None"
        weaknesses_formatted = ", ".join(weak_subjects) if weak_subjects else "None"
        average_formatted = ", ".join(average_areas) if average_areas else "None"
    
        prompt = MCQ_PROMPT_WITH_REPORT.format(
            strengths=strengths_formatted,
            weaknesses=weaknesses_formatted,
            average = average_formatted
        ) if strong_areas or weak_areas else MCQ_PROMPT_WITHOUT_REPORT
        mcq_generator = get_mcq_generator(model)

        full_paths = []
        for file in files:
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            full_paths.append(file_path)
        
        mcqs = mcq_generator.generate_personalized_mcqs(prompt, full_paths)

        if not mcqs:
            raise HTTPException(status_code=500, detail="Failed to generate MCQs")
        
        mcqs = mcqs.strip()
        json_match = re.search(r"```json\n(.*?)\n```", mcqs, re.DOTALL)
        mcq_data = json_match.group(1).strip() if json_match else mcqs.strip()

        try:
            mcq_data = json.loads(mcq_data)
        except json.JSONDecodeError as e:
            print("❌ JSON Parsing Error:", e)
            print("Raw MCQ Response:", mcqs)
            raise HTTPException(status_code=500, detail="Failed to parse MCQs")
        
        formatted_mcqs = [
            {
                "topic": mcq["Topic"],
                "question": mcq["Question"],
                "options": mcq["Options"],
                "correct_answer": mcq["Correct Answer"] 
            }
            for mcq in mcq_data
        ]

        return formatted_mcqs

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for file_path in files:
            file_path = os.path.join(UPLOAD_DIR, file_path.filename)
            if os.path.exists(file_path):
                os.remove(file_path)


class UserAnswer(BaseModel):
    topic: str
    correct: int
    total: int

@router.post("/mcqs/update-report/")
async def update_user_report_based_on_answers(
    answers: List[UserAnswer], token: str = Depends(oauth2_scheme)
):
    """Updates or creates a user's strengths & weaknesses report based on MCQ answers."""
    try:
        decoded_data = await decode_access_token(token)
        user_id = decoded_data["payload"].get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        latest_report_id = user.get("latest_report_id")
        strengths = set()
        average = set()
        weaknesses = {}

        
        if latest_report_id:
            report = reports_collection.find_one({"_id": ObjectId(latest_report_id)})
            if report:
                strengths = set(report.get("strengths", []))
                average = set(report.get("average",[]))
                weaknesses = {w["subject"]: w["reason"] for w in report.get("weaknesses", [])}
                

        
        for answer in answers:
            topic = answer.topic
            accuracy = answer.correct / answer.total if answer.total > 0 else 0

            if accuracy >= 0.75:
                weaknesses.pop(topic, None)  
                strengths.add(topic)
            elif  0.5 <= accuracy < 0.75:
                weaknesses.pop(topic, None)  
                strengths.discard(topic)  
                average.add(topic) 
            elif accuracy < 0.5:
                weaknesses[topic] = f"Low accuracy in MCQs (equals to {accuracy}%)"
                strengths.discard(topic)  

        
        weaknesses_list = [{"subject": k, "reason": v} for k, v in weaknesses.items()]

        if latest_report_id:
            
            reports_collection.update_one(
                {"_id": ObjectId(latest_report_id)},
                {"$set": {"strengths": list(strengths),"average":list(average), "weaknesses": weaknesses_list}}
            )
        else:
            
            student_report = {
                "user_id": user_id,
                "strengths": list(strengths),
                "average":list(average),
                "weaknesses": weaknesses_list,
            }
            report_result = reports_collection.insert_one(student_report)
            new_report_id = str(report_result.inserted_id)

            
            update_result = users_collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"latest_report_id": new_report_id}}
            )

            if update_result.modified_count == 0:
                raise HTTPException(status_code=404, detail="Failed to link report to user")

            student_report["_id"] = new_report_id

        return {
            "message": "User report updated successfully",
            "strengths": list(strengths),
            "average":list(average),
            "weaknesses": weaknesses_list
        }

    except Exception as e:
        print("❌ Error in update_user_report_based_on_answers:", str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/flashcards/")
async def generate_flashcards(files: List[UploadFile] = File(...),model: str = Form(...)):
    """Generates flashcards directly from uploaded files."""
    
    full_paths = []
    try:
        for file in files:
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            full_paths.append(file_path)

        for path in full_paths:
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail=f"File not found: {path}")

        if model == "chatgpt":
            flashcard_generator = FlashcardGeneratorChatGPT()
        elif model == "gemini":
            flashcard_generator = FlashcardGeneratorGemini()
        elif model == "mistral":
            flashcard_generator = FlashcardGeneratorMistral()
        else:
            raise HTTPException(status_code=400, detail="Invalid model specified")

        flashcards = flashcard_generator.generate_flashcards(file_paths=full_paths)

        if isinstance(flashcards, list):
            return {"flashcards": flashcards}
        else:
            raise HTTPException(status_code=500, detail="Failed to generate flashcards")
    finally:
        for file_path in files:
            file_path = os.path.join(UPLOAD_DIR, file_path.filename)
            if os.path.exists(file_path):
                os.remove(file_path)

@router.post("/flashcards/personalized/")
async def generate_personalized_flashcards(
    model: str = Form(...),
    files: List[UploadFile] = File(...),
    token: str = Depends(oauth2_scheme)
):
    try:
        decoded_data = await decode_access_token(token)
        user_id = decoded_data["payload"].get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user_data = dict(user)

        latest_report = None
        if "latest_report_id" in user_data:
            report = reports_collection.find_one({"_id": ObjectId(user_data["latest_report_id"])})
            if report:
                latest_report = dict(report)

        weak_areas = latest_report.get("weaknesses", []) if latest_report else []
        strong_areas = latest_report.get("strengths", []) if latest_report else []
        average_areas = latest_report.get("average",[]) if latest_report else []
        
        weak_subjects = [area["subject"] for area in weak_areas] if weak_areas else []
        strengths_formatted = ", ".join(strong_areas) if strong_areas else "None"
        weaknesses_formatted = ", ".join(weak_subjects) if weak_subjects else "None"
        average_formatted = ", ".join(average_areas) if average_areas else "None"
        print("here is the prompt")
        prompt = FLASHCARD_PROMPT_WITH_REPORT.format(
            strengths=strengths_formatted,
            weaknesses=weaknesses_formatted,
            average = average_formatted
        ) if strong_areas or weak_areas else FLASHCARD_PROMPT

        full_paths = []
        for file in files:
            file_path = os.path.join(UPLOAD_DIR, file.filename)
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            full_paths.append(file_path)

        for path in full_paths:
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail=f"File not found: {path}")

        if model == "chatgpt":
            flashcard_generator = FlashcardGeneratorChatGPT()
        elif model == "gemini":
            flashcard_generator = FlashcardGeneratorGemini()
        elif model == "mistral":
            flashcard_generator = FlashcardGeneratorMistral()
        else:
            raise HTTPException(status_code=400, detail="Invalid model specified")

        flashcards = flashcard_generator.generate_flashcards_with_report(file_paths=full_paths,prompt=prompt)

        if isinstance(flashcards, list):
            return {"flashcards": flashcards}
        else:
            raise HTTPException(status_code=500, detail="Failed to generate flashcards")
    finally:
        for file_path in files:
            file_path = os.path.join(UPLOAD_DIR, file_path.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                
@router.post("/upload/")
async def upload_document(file: UploadFile = File(...), model: str = Form("gemini")):
    """Uploads a document and stores it for later summarization with the selected model."""
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    if model not in CHAT_SERVICES:
        raise HTTPException(status_code=400, detail=f"Invalid model. Choose from {list(CHAT_SERVICES.keys())}")

    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        chat_service = CHAT_SERVICES[model]
        chat_service.load_file(file_path)
        logging.info(f"File '{file.filename}' saved successfully for model '{model}'.")
        return JSONResponse(
            status_code=200,
            content={"message": "File uploaded successfully", "file_path": file_path, "model": model}
        )
    except Exception as e:
        logging.error(f"Error uploading file for model '{model}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_path):
                os.remove(file_path)

@router.post("/ask/")
async def ask_question(query: str = Form(...), model: str = Form("gemini")):
    """Asks a question about the uploaded document using the selected model."""
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    
    if model not in CHAT_SERVICES:
        raise HTTPException(status_code=400, detail=f"Invalid model. Choose from {list(CHAT_SERVICES.keys())}")

    chat_service = CHAT_SERVICES[model]
    return chat_service.ask_question(query)
