import time
import logging
from openai import OpenAI
from langchain_openai import ChatOpenAI
from core.config import OPENAI_API_KEY
from core.prompts import SUMMARY_PROMPT as CHATGPT_PROMPT, OLD_Prompt
from langchain.memory import ConversationBufferMemory
from langchain_community.chat_message_histories import ChatMessageHistory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4", openai_api_key=OPENAI_API_KEY)
        self.client = OpenAI() 
        self.summary = None 
        
        self.chat_history = ChatMessageHistory()
        self.memory = ConversationBufferMemory(chat_memory=self.chat_history, return_messages=True)

    def load_pdf(self, pdf_path: str):
        """Generate summary using ChatGPT and store it."""
        logger.info(f"Processing document: {pdf_path}")
        self.summary = self.chatGPT_Summary(pdf_path)
        if self.summary:
            logger.info("Summary generated successfully.")
            return self.summary
        else:
            logger.warning("Failed to generate summary.")

    def ask_question(self, query: str):

        if not self.summary:
            return {"error": "No document summary available. Please upload a document first."}

        self.memory.chat_memory.add_user_message(query)

        memory_data = self.memory.load_memory_variables({})
        logger.info(f"Memory Data: {memory_data}")  

        chat_history_key = "history" if "history" in memory_data else "chat_history"
        
        if chat_history_key not in memory_data:
            return {"error": "Chat history is not available."}

        chat_prompt = (
            "You are an AI that answers strictly based on the document summary provided below. "
            "If the user asks anything unrelated, politely say you can only answer questions about the document.\n\n"
            f"Document Summary:\n{self.summary}\n\n"
            f"Previous Chat History:\n{memory_data[chat_history_key]}\n\n"
            f"User Query: {query}\n\n"
            "Answer only based on the document summary above."
        )

        response = self.llm.invoke(chat_prompt)

        if hasattr(response, "content"):
            answer = response.content
        else:
            answer = str(response)

        self.memory.chat_memory.add_ai_message(answer) 
        
        return {"answer": answer}


    def chatGPT_Summary(self, file_path: str):
        """Generates a section-wise summary of the provided file using ChatGPT."""
        if not file_path:
            raise ValueError("File path cannot be empty.")

        logger.info("ChatGPT Summary is executing...")

        try:
            with open(file_path, "rb") as file:
                uploaded_file = self.client.files.create(file=file, purpose="assistants")

            file_id = uploaded_file.id  
            logger.info(file_id)

            assistant = self.client.beta.assistants.create(
                name="Dynamic File Processing Assistant",
                instructions=CHATGPT_PROMPT,  
                model="gpt-4o-mini",
                tools=[{"type": "file_search"}],  
            )

            thread = self.client.beta.threads.create()

            message = self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content="I want a Notes of the whole file which I attached section by section as per my prompt",
                attachments=[{"file_id": file_id, "tools": [{"type": "file_search"}]}], 
            )

            run = self.client.beta.threads.runs.create(
                thread_id=thread.id, assistant_id=assistant.id
            )

            while True:
                time.sleep(1)
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=thread.id, run_id=run.id
                )
                if run_status.status in ["completed", "failed"]:
                    break

            messages = self.client.beta.threads.messages.list(thread_id=thread.id)
            content = next(
                (msg.content[0].text.value for msg in messages.data if msg.role == "assistant"), "No summary found."
            )
            print(content)
            return content

        except Exception as err:
            logger.error(f"Exception occurred in ChatGPT extraction: {err}")
            return "Error generating summary"

