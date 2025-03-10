import os
import json
import faiss
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.docstore.in_memory import InMemoryDocstore
from langchain.schema import Document

FAISS_INDEX_PATH = "faiss_index"
DOCS_FILE = os.path.join(FAISS_INDEX_PATH, "docs.json")
INDEX_FILE = os.path.join(FAISS_INDEX_PATH, "vector_store.index")


class VectorStoreService:
    """Manages FAISS vector storage with persistence and incremental updates."""

    def __init__(self):
        os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
        self.embeddings = OpenAIEmbeddings()
        self.vectorstore = None
        self.load_vectorstore()

    def process_and_store(self, pdf_path: str):
        """Loads PDF, splits text, and stores vectors in FAISS."""
        docs = PyPDFLoader(pdf_path).load()
        chunks = []

        for doc in docs:
            page_number = doc.metadata.get("page", 1)
            splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
            split_chunks = splitter.split_text(doc.page_content)

            for chunk in split_chunks:
                chunks.append(Document(page_content=chunk, metadata={"page": page_number}))

        if not chunks:
            print("No text chunks extracted.")
            return

        new_store = FAISS.from_documents(chunks, self.embeddings)
        self.vectorstore = new_store  # Replace old vectorstore completely

        self.save_vectorstore(chunks)

    def save_vectorstore(self, docs):
        """Saves FAISS index and documents to disk."""
        if self.vectorstore:
            faiss.write_index(self.vectorstore.index, INDEX_FILE)
            with open(DOCS_FILE, "w") as f:
                json.dump([{"page_content": doc.page_content, "metadata": doc.metadata} for doc in docs], f)
            print(f"FAISS index saved with {len(docs)} documents.")
            self.load_vectorstore()  # Ensure updated data is loaded

    def load_vectorstore(self):
        """Loads FAISS index and documents from disk."""
        if os.path.exists(INDEX_FILE) and os.path.exists(DOCS_FILE):
            try:
                index = faiss.read_index(INDEX_FILE)
                with open(DOCS_FILE, "r") as f:
                    docs = [Document(**doc) for doc in json.load(f)]

                if index.ntotal != len(docs):
                    print("Mismatch detected: Rebuilding index.")
                    self.vectorstore = FAISS.from_documents(docs, self.embeddings)
                    self.save_vectorstore(docs)
                    return

                docstore = InMemoryDocstore({str(i): doc for i, doc in enumerate(docs)})
                index_to_docstore_id = {i: str(i) for i in range(len(docs))}

                self.vectorstore = FAISS(
                    index=index,
                    embedding_function=self.embeddings,
                    docstore=docstore,
                    index_to_docstore_id=index_to_docstore_id
                )
                print(f"Loaded FAISS index with {len(docs)} documents.")
            except Exception as e:
                print(f"Error loading FAISS index: {e}. Reinitializing index.")
                self.vectorstore = None
        else:
            print("No FAISS index found. Initializing empty vector store.")
            self.vectorstore = None

    def get_vectorstore(self):
        """Returns the FAISS vector store."""
        return self.vectorstore

    def get_content_by_page(self, page_number: int):
        """Retrieves content from a specific page."""
        if not self.vectorstore or not self.vectorstore.docstore:
            return "No document uploaded yet."

        stored_pages = sorted({doc.metadata.get("page") for doc in self.vectorstore.docstore._dict.values()})
        
        docs = [
            doc.page_content 
            for doc in self.vectorstore.docstore._dict.values() 
            if doc.metadata.get("page") == page_number
        ]

        if docs:
            return "\n".join(docs)
        
        return f"No content found on page {page_number}. Available pages: {stored_pages}"

    def debug_stored_pages(self):
        """Prints stored page numbers for debugging."""
        if not self.vectorstore or not self.vectorstore.docstore:
            print("No documents are currently stored.")
            return []
        
        stored_pages = sorted({doc.metadata.get("page") for doc in self.vectorstore.docstore._dict.values()})
        print(f"Stored pages: {stored_pages}")
        return stored_pages