import re
import os
import json
import faiss
import spacy
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.docstore.in_memory import InMemoryDocstore
from langchain.schema import Document
from core.config import OPENAI_API_KEY

FAISS_INDEX_PATH = "faiss_index"
DOCS_FILE = os.path.join(FAISS_INDEX_PATH, "docs.json")
INDEX_FILE = os.path.join(FAISS_INDEX_PATH, "vector_store.index")

nlp = spacy.load("en_core_web_sm")

class DocumentChatService:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=OPENAI_API_KEY)
        self.embeddings = OpenAIEmbeddings()
        self.memory = ConversationBufferMemory(memory_key="chat_history", output_key="answer", return_messages=True)
        self.vectorstore = None
        self.page_content_map = {}
        self.load_vectorstore()

        self.custom_prompt = PromptTemplate(
            input_variables=["context", "question"],
            template="""
            You are a **precise and reliable exam assistant**. Your task is to answer questions **strictly based on the provided document** without adding any external information.

            ## **Instructions**  
            - **Use only the given context** to generate responses.  
            - **Definitions, examples, problems, and solutions must be identical** to those in the document—do not alter or rephrase them.  
            - If the document contains **step-by-step solutions**, provide them exactly as presented.  
            - If a question refers to concepts covered in the document, summarize concisely **without adding interpretations** beyond what is explicitly stated.  
            - If the document does not contain the requested information, respond with:  
            **"I couldn't find relevant information in the uploaded document."**  

            ## **Response Format**  
            - **Retain original terminology** from the document.  
            - **Maintain mathematical notation and formatting** for clarity.  
            - If necessary, **use bullet points or structured formatting** to improve readability.  

            **Question:** {question}  
            **Context:** {context}  
            """
        )


        self.ORDINAL_MAP = {
            "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
            "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
            "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
            "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
            "nineteenth": 19, "twentieth": 20
        }

    def extract_page_number(self, query: str):
        """Extracts page number using regex first, then NLP with ordinal word mapping."""
        match = re.search(r'(?:on|from)?\s?(?:the)?\s?(\d{1,3})(?:st|nd|rd|th)?\s?(?:page)', query, re.IGNORECASE)
        if match:
            return int(match.group(1))

        doc = nlp(query)
        for token in doc:
            if token.text.lower() in ["page", "pages"] and token.i > 0:
                prev_token = doc[token.i - 1]
                if prev_token.like_num:
                    return int(prev_token.text)
                elif prev_token.text.lower() in self.ORDINAL_MAP:
                    return self.ORDINAL_MAP[prev_token.text.lower()]

        return None


    def load_pdf(self, pdf_path: str):
        """Loads and processes a new PDF, replacing any existing data."""
        self.page_content_map.clear()
        docs = PyPDFLoader(pdf_path).load()
        chunks = []

        for doc in docs:
            page_number = doc.metadata.get("page", 1)
            splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
            split_chunks = splitter.split_text(doc.page_content)

            for chunk in split_chunks:
                chunks.append(Document(page_content=chunk, metadata={"page": page_number}))

            self.page_content_map[page_number] = doc.page_content

        if not chunks:
            print("No text chunks extracted.")
            return

        self.vectorstore = FAISS.from_documents(chunks, self.embeddings)
        self.save_vectorstore(chunks)

    def save_vectorstore(self, docs):
        """Saves FAISS index and documents."""
        if self.vectorstore:
            faiss.write_index(self.vectorstore.index, INDEX_FILE)
            with open(DOCS_FILE, "w") as f:
                json.dump([{"page_content": doc.page_content, "metadata": doc.metadata} for doc in docs], f)
            self.load_vectorstore()

    def load_vectorstore(self):
        """Loads FAISS index and documents from disk."""
        if os.path.exists(INDEX_FILE) and os.path.exists(DOCS_FILE):
            try:
                index = faiss.read_index(INDEX_FILE)
                with open(DOCS_FILE, "r") as f:
                    docs = [Document(**doc) for doc in json.load(f)]

                docstore = InMemoryDocstore({str(i): doc for i, doc in enumerate(docs)})
                index_to_docstore_id = {i: str(i) for i in range(len(docs))}

                self.vectorstore = FAISS(
                    index=index,
                    embedding_function=self.embeddings,
                    docstore=docstore,
                    index_to_docstore_id=index_to_docstore_id
                )
            except Exception as e:
                print(f"Error loading FAISS index: {e}. Reinitializing index.")
                self.vectorstore = None
        else:
            self.vectorstore = None

    def ask_question(self, query: str):
        """Answers queries using vector search and page lookup."""
        if not self.vectorstore:
            return {"error": "No document uploaded yet."}

        page_number = self.extract_page_number(query)

        if page_number and page_number in self.page_content_map:
            response = self.llm.predict(f"Summarize the following content and answer the user's question: {self.page_content_map[page_number]}\nQuestion: {query}")
            return {"answer": response}

        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 10})
        retrieved_docs = retriever.get_relevant_documents(query)

        if not retrieved_docs:
            return {"answer": "No relevant information found."}

        conversation_chain = ConversationalRetrievalChain.from_llm(
            llm=self.llm,
            retriever=retriever,
            memory=self.memory,
            return_source_documents=True,
            combine_docs_chain_kwargs={"prompt": self.custom_prompt}
        )

        response = conversation_chain.invoke({"question": query, "chat_history": self.memory.load_memory_variables({})["chat_history"]})
        return {"answer": response.get("answer", "I couldn't find relevant information in the uploaded document.")}

    def debug_pages(self):
        """Prints available page numbers for debugging."""
        print(f"Stored pages: {sorted(self.page_content_map.keys())}")
        return sorted(self.page_content_map.keys())
