from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from services.vector_store import VectorStoreService
from core.config import OPENAI_API_KEY
from langchain_openai import ChatOpenAI

class ChatService:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=OPENAI_API_KEY)
        self.vector_service = VectorStoreService()
        self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    def load_pdf(self, pdf_path: str):
        """Load and store document vectors"""
        self.vector_service.process_and_store(pdf_path)

    def ask_question(self, query: str):
        """Answer queries based on uploaded document while maintaining context"""
        vectorstore = self.vector_service.get_vectorstore()
        if vectorstore is None:
            return {"error": "No document uploaded yet."}

        retriever = vectorstore.as_retriever()
        conversation_chain = ConversationalRetrievalChain.from_llm(
            llm=self.llm,
            retriever=retriever,
            memory=self.memory
        )

        response = conversation_chain.run(query)
        return {"answer": response}
