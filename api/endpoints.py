from fastapi import APIRouter, UploadFile, File, Form
import shutil
import os
from services.chat import ChatService
from fastapi import HTTPException
import logging
from fastapi.responses import JSONResponse
from services.documents import process_pdf
logger = logging.getLogger(__name__)

router = APIRouter()
chat_service_v1 = ChatService()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload/")
async def upload_document(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print("File saved successfully. Now loading PDF...")
        summary = chat_service_v1.load_pdf(file_path)
        print("PDF loaded successfully.")
        logger.info(f"File {file.filename} uploaded and processed successfully.")
        return {"summary": summary,"message":"document uploaded sucessfully"}

    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    

@router.post("/ask/")
async def ask_question(query: str = Form(...)):
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return chat_service_v1.ask_question(query)
