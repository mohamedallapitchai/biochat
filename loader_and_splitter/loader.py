import logging
import os
import tempfile
import threading
from typing import List

import boto3
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)
docs: List[Document]  = []


def load_docs() -> List[Document]:
    global docs
    bucket: str = "biochat"
    prefix: str = "bio/"
    exts = (".pdf", ".txt")
    if len(docs) == 0:
        logger.info(f"docs is none")
        _build_lock = threading.Lock()
        with _build_lock:
            s3 = boto3.client("s3")
            docs = []
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []) or []:
                    key = obj["Key"]
                    if key.endswith("/") or not key.lower().endswith(exts):
                        continue
                    suffix = os.path.splitext(key)[1].lower()
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        s3.download_fileobj(bucket, key, tmp)
                        path = tmp.name
                    try:
                        if suffix == ".pdf":
                            loader = PyPDFLoader(path)
                        else:
                            loader = TextLoader(path, encoding="utf-8")
                        file_docs = loader.load()
                        for d in file_docs:
                            d.metadata.setdefault("source", f"s3://{bucket}/{key}")
                        docs.extend(file_docs)
                    finally:
                        try:
                            os.unlink(path)
                        except OSError:
                            pass
                return docs
    else:
        logger.info(f"docs is not empty")
        return docs

    # def load_docs():


#     global docs
#     if docs is None:
#         logger.info(f"docs is none")
#         _build_lock = threading.Lock()
#         with _build_lock:
#             loader = S3DirectoryLoader(bucket="biochat", prefix="bio/")
#             docs = loader.load()
#             return docs
#     else:
#         logger.info(f"docs is already loaded")
#         return docs


parent_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, add_start_index=True)
# This text splitter is used to create the child documents
# It should create documents smaller than the parent
child_splitter = RecursiveCharacterTextSplitter(chunk_size=400, add_start_index=True)
