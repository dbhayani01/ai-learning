from langchain_community.document_loaders import PyPDFDirectoryLoader

from chunking.recursive import get_chunks
from vectordb.faiss_store import create_or_update_vector_store

import shutil
import os

DB_PATH = "faiss_index"

# Delete old index
if os.path.exists(DB_PATH):
    shutil.rmtree(DB_PATH)
    print("Old FAISS index removed")

# Load all PDFs
loader = PyPDFDirectoryLoader("documents")
documents = loader.load()

print(f"Loaded {len(documents)} pages")

# Re-chunk using new strategy
chunks = get_chunks(documents)

print(f"Created {len(chunks)} chunks")

# Create fresh vector store
create_or_update_vector_store(chunks)

print("Re-indexing completed")
