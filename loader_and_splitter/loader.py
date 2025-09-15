import logging
import os
import tempfile
import threading
from typing import List, Optional

import boto3
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from botocore.exceptions import ClientError
from dotenv import load_dotenv



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)
_docs_cache: Optional[List[Document]] = None   # sentinel: not loaded yet
_docs_lock = threading.Lock()


def load_docs() -> List[Document]:
    global _docs_cache
    bucket: str = os.getenv("BUCKET_NAME")
    prefix = os.getenv("BUCKET_BIO_KEY")
    exts = (".pdf", ".txt")
    if _docs_cache is not None:
        return _docs_cache
    with _docs_lock:
        s3 = boto3.client("s3")
        docs: List[Document] = []
        n_keys = 0

        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                key = obj["Key"]
                print(f"key is {key}")
                if key.endswith("/") or not key.lower().endswith(exts):
                    continue
                n_keys += 1
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
            logger.info("Loaded %d files; produced %d documents", n_keys, len(docs))
            _docs_cache = docs
            return _docs_cache


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


parent_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, add_start_index=True, chunk_overlap=200,
                                                 separators=["\n", "\n\n", "\n\n\n"])
# This text splitter is used to create the child documents
# It should create documents smaller than the parent
child_splitter = RecursiveCharacterTextSplitter(chunk_size=400, add_start_index=True, chunk_overlap=80,
                                                separators=["\n", "\n\n", "\n\n\n", "EDUCATION"])


def generate_presigned_url(s3_client, client_method, method_parameters, expires_in):
    """
    Generate a presigned Amazon S3 URL that can be used to perform an action.

    :param s3_client: A Boto3 Amazon S3 client.
    :param client_method: The name of the client method that the URL performs.
    :param method_parameters: The parameters of the specified client method.
    :param expires_in: The number of seconds the presigned URL is valid for.
    :return: The presigned URL.
    """
    try:
        url = s3_client.generate_presigned_url(
            ClientMethod=client_method,
            Params=method_parameters,
            ExpiresIn=expires_in
        )
    except ClientError:
        print(f"Couldn't get a presigned URL for client method '{client_method}'.")
        raise
    return url

if __name__ == "__main__":
    load_dotenv()
    s3_client = boto3.client("s3")
    bucket_name = os.getenv("BUCKET_NAME")
    bucket_key = os.getenv("BUCKET_KEY")

    # The presigned URL is specified to expire in 1000 seconds
    url = generate_presigned_url(
        s3_client,
        "get_object",
        {"Bucket": bucket_name, "Key": bucket_key},
        1000
    )
    print(f"Generated GET presigned URL: {url}")
