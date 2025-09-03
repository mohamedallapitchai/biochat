import logging
import os
import threading
from functools import lru_cache

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


def _collection_is_empty(client, collection):
    info = client.get_collection(collection)
    return (info.points_count or 0) == 0


def _ingest_if_needed(retriever, client, collection):
    if _collection_is_empty(client, collection):
        # load_docs() → your S3 loader; run once to add children + parents
        retriever.add_documents(load_docs())


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
        logger.info(f"TRYING TO GET RETRIEVER")
        _ingest_if_needed(retr, client, os.environ["QDRANT_COLLECTION"])
    return retr
