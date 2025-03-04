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
    """Manages FAISS vector storage with persistence."""

    def __init__(self):
        os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
        self.embeddings = None
        self.vectorstore = None
        self.load_vectorstore()

    def _get_embeddings(self):
        """Lazy initialization of OpenAI embeddings."""
        if not self.embeddings:
            self.embeddings = OpenAIEmbeddings()
        return self.embeddings

    def process_and_store(self, pdf_path: str):
        """Loads PDF, splits text, and stores vectors in FAISS."""
        docs = PyPDFLoader(pdf_path).load()
        chunks = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_documents(docs)

        if chunks:
            self.vectorstore = FAISS.from_documents(chunks, self._get_embeddings())
            self.save_vectorstore(chunks)  # Save FAISS index and documents

    def save_vectorstore(self, docs):
        """Saves FAISS index and original documents to disk."""
        if self.vectorstore:
            faiss.write_index(self.vectorstore.index, INDEX_FILE)
            with open(DOCS_FILE, "w") as f:
                json.dump([doc.dict() for doc in docs], f)

    def load_vectorstore(self):
        """Loads FAISS index and documents from disk if available."""
        if os.path.exists(INDEX_FILE) and os.path.exists(DOCS_FILE):
            index = faiss.read_index(INDEX_FILE)
            with open(DOCS_FILE, "r") as f:
                docs = [Document(**doc) for doc in json.load(f)]

            docstore = InMemoryDocstore({str(i): doc for i, doc in enumerate(docs)})
            index_to_docstore_id = {i: str(i) for i in range(len(docs))}

            self.vectorstore = FAISS(
                index=index,
                embedding_function=self._get_embeddings(),
                docstore=docstore,
                index_to_docstore_id=index_to_docstore_id
            )

    def get_vectorstore(self):
        """Returns the FAISS vector store."""
        return self.vectorstore
