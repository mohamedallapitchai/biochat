import logging
import os
import threading
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from filelock import FileLock
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import LocalFileStore
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from loader_and_splitter.loader import load_docs, child_splitter, parent_splitter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

_build_lock = threading.Lock()
LOCK_FILE = "/tmp/retriever.build.lock"  # per-container lock


def _collection_is_empty(client, collection: str) -> bool:
    try:
        info = client.get_collection(collection)
        return (info.points_count or 0) == 0
    except Exception:
        # collection might not exist yet
        return True


def _parent_store_missing(parent_store_dir: str) -> bool:
    p = Path(parent_store_dir)
    return not p.exists() or not any(p.glob("**/*"))


def _ingest_if_needed(retriever, client, collection: str, parent_store_dir: str):
    if _collection_is_empty(client, collection) or _parent_store_missing(parent_store_dir):
        docs = load_docs()
        retriever.add_documents(docs)


@lru_cache(maxsize=1)
def get_retriever():
    emb = OpenAIEmbeddings(model="text-embedding-3-small")
    load_dotenv()
    client = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ["QDRANT_API_KEY"])
    vs = QdrantVectorStore(client=client, collection_name=os.environ["QDRANT_COLLECTION"], embedding=emb)
    byte_store = LocalFileStore(os.environ.get("PARENT_STORE_DIR", "./parent_store"))
    retr = ParentDocumentRetriever(vectorstore=vs, byte_store=byte_store,
                                   child_splitter=child_splitter, parent_splitter=parent_splitter)

    # one-time guarded ingest across threads + processes
    with _build_lock, FileLock(LOCK_FILE):
        logger.info(f"RETRIEVER is not in cache, loading docs from s3 and creating retriever")
        _ingest_if_needed(retr, client, os.environ["QDRANT_COLLECTION"], byte_store.root_path)
    return retr
