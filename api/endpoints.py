from fastapi import APIRouter, UploadFile, File, Form
import shutil
import os
from fastapi import HTTPException
import logging
from fastapi.responses import JSONResponse
from services.summary import stream_pdf_summary
logger = logging.getLogger(__name__)
from fastapi.responses import StreamingResponse
from services.chat import DocumentChatService
from services.flashcards import FlashcardGeneratorChatGPT,FlashcardGeneratorMistral,FlashcardGeneratorGemini
import time
from typing import List
router = APIRouter()
chat_service = DocumentChatService()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
from core.config import OPENAI_API_KEY
from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)


@router.post("/upload/")
async def upload_document(file: UploadFile = File(...)):
    """Uploads a document and stores it for later summarization."""
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        chat_service.load_pdf(file_path)
        logging.info(f"File '{file.filename}' saved successfully.")
        return JSONResponse(status_code=200, content={"message": "File uploaded successfully", "file_path": file_path})

    except Exception as e:
        logging.error(f"Error uploading file: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.post("/ask/")
async def ask_question(query: str = Form(...)):
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return chat_service.ask_question(query)


@router.post("/flashcards/")
async def generate_flashcards(
    files: List[UploadFile] = File(...),
    model: str = Form(...)
):
    """Generates flashcards directly from uploaded files."""
    
    full_paths = []
    
    # Save uploaded files
    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        full_paths.append(file_path)

    print("full_paths", full_paths)

    # Check if all files exist
    for path in full_paths:
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"File not found: {path}")

    # Select Model
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

@router.post("/notes/")
async def generate_notes(files: list[UploadFile] = File(...), model: str = Form(...)):
    """Accept multiple PDFs, process them, and return structured notes."""
    
    file_paths = []
    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        file_paths.append(file_path)

    return StreamingResponse(stream_pdf_summary(file_paths,model), media_type="text/event-stream")
