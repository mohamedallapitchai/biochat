import logging
import threading

from typing import List

from langchain_community.document_loaders import S3FileLoader, S3DirectoryLoader, PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)
docs: List[Document] | None = None


def load_docs():
    global docs
    if docs is None:
        logger.info(f"docs is none")
        _build_lock = threading.Lock()
        with _build_lock:
            loader = S3DirectoryLoader(bucket="biochat", prefix="bio/")
            docs = loader.load()
            return docs
    else:
        logger.info(f"docs is already loaded")
        return docs


parent_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, add_start_index=True)
# This text splitter is used to create the child documents
# It should create documents smaller than the parent
child_splitter = RecursiveCharacterTextSplitter(chunk_size=400, add_start_index=True)
