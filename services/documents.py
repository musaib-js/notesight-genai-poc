import os
import asyncio
import time
from openai import AsyncOpenAI
from core.prompts import SUMMARY_PROMPT

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def summarize_text(text: str, retries=5, delay=1):
    """Asynchronously sends text to OpenAI for summarization with retry logic."""
    for i in range(retries):
        try:
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": SUMMARY_PROMPT.format(text=text)}]
            )
            return response.choices[0].message.content
        
        except Exception as e:
            if "429" in str(e):  # Handle rate limits
                wait_time = delay * (2 ** i)  # Exponential backoff
                print(f"Rate limit hit. Retrying in {wait_time:.2f} seconds...")
                await asyncio.sleep(wait_time)
            else:
                print(f"OpenAI API error: {e}")
                return None
    return None  # Return None if all retries fail

async def process_pdf(text_chunks):
    """Process PDF text in chunks and summarize each chunk asynchronously with limited concurrency."""
    semaphore = asyncio.Semaphore(5)  # Adjust the limit based on your OpenAI API rate limit

    async def limited_summarize(chunk):
        async with semaphore:
            return await summarize_text(chunk)

    summaries = await asyncio.gather(*(limited_summarize(chunk) for chunk in text_chunks))
    return " ".join(summaries)
