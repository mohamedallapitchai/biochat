from langchain_community.document_loaders import S3FileLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter


def load_docs():
    loader = S3FileLoader(
        "biochat",
        "bio/mallapitchai.pdf",
        unstructured_kwargs={"strategy": "fast"}  # or use PyPDFLoader path
    )
    return loader.load()


parent_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, add_start_index=True)
# This text splitter is used to create the child documents
# It should create documents smaller than the parent
child_splitter = RecursiveCharacterTextSplitter(chunk_size=400, add_start_index=True)
