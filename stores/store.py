import logging
import threading

from langchain.retrievers import ParentDocumentRetriever
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore

from loader_and_splitter.loader import load_docs, child_splitter, parent_splitter
from langchain.storage import InMemoryStore

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
vector_store = InMemoryVectorStore(embeddings)
store = InMemoryStore()

retriever = None
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

def get_retriever():
    global retriever
    if retriever is None:
        logger.info(f"retriever is none")
        _build_lock = threading.Lock()
        with _build_lock:
            retriever = ParentDocumentRetriever(
                vectorstore=vector_store,
                byte_store=store,
                child_splitter=child_splitter,
                parent_splitter=parent_splitter,
            )
            retriever.add_documents(load_docs())
            return retriever
    else:
        logger.info(f"retriever is {retriever}")
        return retriever
