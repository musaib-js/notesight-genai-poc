import os
import logging
import asyncio
import time
import pdfplumber
from fastapi import FastAPI, UploadFile, File, APIRouter
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from core.config import OPENAI_API_KEY

app = FastAPI()
router = APIRouter()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SUMMARY_PROMPT = """You are an AI assistant that generates structured exam notes. Follow these rules:
1. **Definitions:** Extract them **exactly** as they are.
2. **Summaries:** Summarize **clearly and concisely**.
3. **Explanations:** Break down complex problems step by step.
4. **Formatting:** Use bullet points, headings, and spacing for readability.

Continue summarizing the content below. If previous context is provided, maintain coherence.

{text}"""

async def extract_text(pdf_path: str, start_page: int, end_page: int) -> str:
    """Extract text from PDF pages and log time taken."""
    start_time = time.perf_counter()
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(pdf.pages[i].extract_text() or "" for i in range(start_page, min(end_page, len(pdf.pages))))
    elapsed_time = time.perf_counter() - start_time
    logging.info(f"Extracted text from pages {start_page}-{end_page} in {elapsed_time:.2f} seconds.")
    return text

async def generate_notes_stream(cleaned_text: str, previous_summary: str = ""):
    """Generate structured notes using OpenAI with context from the previous summary."""
    if not cleaned_text:
        yield ""

    start_time = time.perf_counter()
    try:
        messages = [{"role": "user", "content": SUMMARY_PROMPT.format(text=cleaned_text)}]
        
        # Add previous summary as context if available
        if previous_summary:
            messages.insert(0, {"role": "assistant", "content": previous_summary})

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",  
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
            stream=True
        )

        full_summary = ""  # Collect the full response

        async for chunk in response:
            if chunk.choices[0].delta.content:
                full_summary += chunk.choices[0].delta.content
                yield chunk.choices[0].delta.content

    except Exception as e:
        logging.error(f"Streaming Error: {e}")
        yield f"Error: {str(e)}"

    elapsed_time = time.perf_counter() - start_time
    logging.info(f"Generated OpenAI response in {elapsed_time:.2f} seconds.")
    

async def process_chunk(pdf_path: str, start_page: int, end_page: int):
    """Extract and clean text from a chunk of pages asynchronously, and log time taken."""
    start_time = time.perf_counter()
    raw_text = await extract_text(pdf_path, start_page, end_page)
    cleaned_text = raw_text.replace("-\n", "").replace("\n", " ").strip()
    elapsed_time = time.perf_counter() - start_time
    logging.info(f"Processed chunk {start_page}-{end_page} in {elapsed_time:.2f} seconds.")
    return cleaned_text if cleaned_text else None

async def stream_pdf_summary(pdf_path: str):
    """Stream summarized notes for a PDF using OpenAI Streaming API while maintaining context."""
    start_time = time.perf_counter()
    previous_summary = ""  # Initialize empty context

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)

        tasks = [process_chunk(pdf_path, start, min(start + 20, total_pages)) for start in range(0, total_pages, 20)]

        for task in asyncio.as_completed(tasks):
            cleaned_text = await task
            if cleaned_text:
                response_text = ""
                async for chunk in generate_notes_stream(cleaned_text, previous_summary):  
                    response_text += chunk
                    yield chunk  # Stream response to client

                previous_summary = response_text  # Update context for next iteration

    except Exception as e:
        logging.error(f"Streaming error: {e}")
        yield f"Error: {str(e)}"
    
    elapsed_time = time.perf_counter() - start_time
    logging.info(f"Total PDF processing time: {elapsed_time:.2f} seconds.")
