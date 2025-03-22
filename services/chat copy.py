import re
import os
import json
import spacy
import chromadb
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document
from core.config import OPENAI_API_KEY  

nlp = spacy.load("en_core_web_sm")

class DocumentChatService:
    def __init__(self, collection_name="document-chat-collection"):
        self.llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=OPENAI_API_KEY)
        self.embeddings = OpenAIEmbeddings()
        self.memory = ConversationBufferMemory(memory_key="chat_history", output_key="answer", return_messages=True)
        self.page_content_map = {}

        # Initialize Chroma client (in-memory by default, can be made persistent with a path)
        self.client = chromadb.Client()  # For demo; use chromadb.PersistentClient(path="chroma_db") for persistence
        self.collection_name = collection_name

        # Create or get the Chroma collection (equivalent to Pinecone index)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )

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
        """Loads and processes a new PDF, replacing any existing data in Chroma."""
        self.page_content_map.clear()
        docs = PyPDFLoader(pdf_path).load()
        chunks = []

        for doc in docs:
            page_number = doc.metadata.get("page", 1)
            splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
            split_chunks = splitter.split_text(doc.page_content)

            for i, chunk in enumerate(split_chunks):
                chunks.append(Document(page_content=chunk, metadata={"page": page_number, "chunk_id": i}))
            self.page_content_map[page_number] = doc.page_content

        if not chunks:
            print("No text chunks extracted.")
            return

        # Generate embeddings and upsert to Chroma
        self._upsert_to_chroma(chunks)

    def _upsert_to_chroma(self, docs):
        """Upserts document chunks to Chroma."""
        embeddings = [self.embeddings.embed_query(doc.page_content) for doc in docs]
        ids = [f"doc_{i}" for i in range(len(docs))]
        metadatas = [{"page": doc.metadata["page"], "text": doc.page_content} for doc in docs]

        # Clear existing data in the collection (optional, remove if you want to append)
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(name=self.collection_name, metadata={"hnsw:space": "cosine"})

        # Add vectors to Chroma
        self.collection.add(
            embeddings=embeddings,
            ids=ids,
            metadatas=metadatas
        )
        print(f"Upserted {len(embeddings)} vectors to Chroma.")

    def ask_question(self, query: str):
        """Answers queries using Chroma vector search and page lookup."""
        page_number = self.extract_page_number(query)

        if page_number and page_number in self.page_content_map:
            response = self.llm.predict(f"Summarize the following content and answer the user's question: {self.page_content_map[page_number]}\nQuestion: {query}")
            return {"answer": response}

        # Generate query embedding
        query_embedding = self.embeddings.embed_query(query)

        # Query Chroma
        search_results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=10,  # Retrieve top 10 similar vectors
            include=["metadatas", "documents"]
        )

        if not search_results["ids"][0]:  # Check if any results were returned
            return {"answer": "I couldn't find relevant information in the uploaded document."}

        # Extract context from search results
        context = "\n".join([doc for doc in search_results["documents"][0]])

        # Use ConversationalRetrievalChain with custom retriever
        from langchain_core.retrievers import BaseRetriever
        class ChromaRetriever(BaseRetriever):
            def __init__(self, collection, embeddings):
                self.collection = collection
                self.embeddings = embeddings

            def _get_relevant_documents(self, query: str):
                query_embedding = self.embeddings.embed_query(query)
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=10,
                    include=["metadatas", "documents"]
                )
                return [Document(page_content=doc, metadata={"page": meta["page"]}) 
                        for doc, meta in zip(results["documents"][0], results["metadatas"][0])]

        retriever = ChromaRetriever(self.collection, self.embeddings)
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

# Example usage
if __name__ == "__main__":
    service = DocumentChatService()
    service.load_pdf("example.pdf")  # Replace with your PDF path
    response = service.ask_question("What is on the second page?")
    print(response)