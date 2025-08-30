from langchain.retrievers import ParentDocumentRetriever
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore

from loader_and_splitter.loader import docs, child_splitter, parent_splitter
from langchain.storage import InMemoryStore

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
vector_store = InMemoryVectorStore(embeddings)
store = InMemoryStore()
retriever = ParentDocumentRetriever(
    vectorstore=vector_store,
    byte_store=store,
    child_splitter=child_splitter,
    parent_splitter=parent_splitter,
)
retriever.add_documents(docs)