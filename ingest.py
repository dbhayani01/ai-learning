from langchain_community.document_loaders import PyPDFDirectoryLoader
from chunking.recursive import get_chunks
from vectordb.faiss_store import create_vector_store


loader = PyPDFDirectoryLoader("documents")

documents = loader.load()

chunks = get_chunks(documents)

print(f"Loaded {len(documents)} pages")
print(f"Created {len(chunks)} chunks")

create_vector_store(chunks)

print("FAISS index created successfully")
