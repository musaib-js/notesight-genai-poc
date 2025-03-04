from fastapi import APIRouter, UploadFile, File, Form
import shutil
import os
from fastapi import HTTPException
import logging
from fastapi.responses import JSONResponse
#from services.documents import process_pdf
from services.summary import stream_pdf_summary
logger = logging.getLogger(__name__)
from fastapi.responses import StreamingResponse
from services.chat import ChatService
router = APIRouter()
chat_service = ChatService()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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

@router.get("/summary/")
async def generate_summary(file_path: str):
    """Generates a summary for the uploaded document."""
    full_path = os.path.join(UPLOAD_DIR, file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    return StreamingResponse(stream_pdf_summary(full_path), media_type="text/event-stream")
    

@router.post("/ask/")
async def ask_question(query: str = Form(...)):
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return chat_service.ask_question(query)
