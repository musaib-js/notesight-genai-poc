from fastapi import FastAPI, UploadFile, File, Form, APIRouter
from fastapi.responses import StreamingResponse
import os
import asyncio
import logging
import pdfplumber
from openai import AsyncOpenAI
from mistralai import Mistral
from core.config import OPENAI_API_KEY, MISTRAL_API_KEY,GEMINI_API_KEY
from google import genai
router = APIRouter()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize OpenAI and Mistral Clients
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

SUMMARY_PROMPT = """You are a STEM expert specializing in **structured note-taking** from text extracted in chunks. 
I will provide content that needs to be converted into **clear, concise, and well-organized notes** without any 
introductory summaries. Your task is to create structured notes that maintain continuity across chunks while 
capturing key points effectively.

### **Guidelines:**  
1. **Definitions:** Extract them **verbatim** without modification.  
2. **Summaries:** Condense content **clearly and concisely**, focusing on key points.  
3. **Explanations:** Break down complex problems **step by step** for clarity.  
4. **Formatting:**  
   - Use **bullet points, headings, and spacing** for readability.  
   - **Ensure continuity** between chunks without redundancy.  
   - **No introductory or concluding summaries**—only structured notes.  
   - Highlight important terms where necessary.  
5. Notes should be like a study guide for exam preparation.

### **Continue processing the next chunk of text:**  
{text}
"""

async def extract_text(pdf_path: str, start_page: int, end_page: int) -> str:
    """Extract text from PDF pages."""
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(pdf.pages[i].extract_text() or "" for i in range(start_page, min(end_page, len(pdf.pages))))
    return text

async def generate_notes_stream_chatgpt(cleaned_text: str, previous_summary: str = ""):
    """Generate structured notes using OpenAI with streaming."""
    if not cleaned_text:
        yield ""

    try:
        messages = [{"role": "user", "content": SUMMARY_PROMPT.format(text=cleaned_text)}]

        if previous_summary:
            messages.insert(0, {"role": "assistant", "content": previous_summary})

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
            stream=True
        )

        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        logging.error(f"ChatGPT Streaming Error: {e}")
        yield f"Error: {str(e)}"

async def generate_notes_stream_mistral(cleaned_text: str):
    """Generate structured notes using Mistral AI with streaming."""
    try:
        response = await mistral_client.chat.stream_async(
            model="mistral-medium",
            messages=[{"role": "user", "content": f"Generate notes from this content without missing any point:\n\n{cleaned_text}"}]
        )

        async for chunk in response:
            if chunk.data.choices[0].delta.content:
                yield chunk.data.choices[0].delta.content

    except Exception as e:
        logging.error(f"Mistral Streaming Error: {e}")
        yield f"Error: {str(e)}"

async def generate_gemini_notes_stream(cleaned_text: str, previous_summary: str = ""):
    """Generate structured notes using Gemini AI with streaming."""
    client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})
    model = "gemini-2.0-flash-exp"
    config = {"response_modalities": ["TEXT"]}
    if not cleaned_text:
        yield ""

    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            message = SUMMARY_PROMPT.format(text=cleaned_text)

            # Send the input message
            await session.send(input=message, end_of_turn=True)

            full_summary = ""

            # Stream the response as it arrives
            async for response in session.receive():
                if response.text is not None:
                    full_summary += response.text
                    yield response.text  # Streaming response to client

    except Exception as e:
        logging.error(f"Gemini Streaming Error: {e}")
        yield f"Error: {str(e)}"

async def process_chunk(pdf_path: str, start_page: int, end_page: int):
    """Extract and clean text from a chunk of pages asynchronously."""
    raw_text = await extract_text(pdf_path, start_page, end_page)
    cleaned_text = raw_text.replace("-\n", "").replace("\n", " ").strip()
    return cleaned_text if cleaned_text else None

async def stream_pdf_summary(pdf_paths: list[str], model: str):
    """Stream summarized notes for multiple PDFs using OpenAI, Mistral, or Gemini."""
    previous_summary = ""

    for pdf_path in pdf_paths:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)

            # Process chunks in order
            for start in range(0, total_pages, 20):
                cleaned_text = await process_chunk(pdf_path, start, min(start + 20, total_pages))

                if cleaned_text:
                    if model == "chatgpt":
                        async for chunk in generate_notes_stream_chatgpt(cleaned_text, previous_summary):
                            yield chunk
                        previous_summary = chunk  # Maintain continuity

                    elif model == "mistral":
                        async for chunk in generate_notes_stream_mistral(cleaned_text):
                            yield chunk
                        previous_summary = chunk  # Maintain context

                    elif model == "gemini":
                        async for chunk in generate_gemini_notes_stream(cleaned_text):
                            yield chunk
                        previous_summary = chunk  # Maintain continuity

        except Exception as e:
            logging.error(f"Streaming error: {e}")
            yield f"Error: {str(e)}"

