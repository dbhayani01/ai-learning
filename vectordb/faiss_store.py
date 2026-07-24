from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FastEmbedEmbeddings
import os

DB_PATH = "faiss_index"

embeddings = FastEmbedEmbeddings()


def create_or_update_vector_store(chunks):
    if os.path.exists(DB_PATH):
        db = FAISS.load_local(
            DB_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )

        db.add_documents(chunks)

    else:
        db = FAISS.from_documents(
            chunks,
            embeddings
        )

    db.save_local(DB_PATH)


def get_vector_store():
    return FAISS.load_local(
        DB_PATH,
        embeddings,
        allow_dangerous_deserialization=True
    )
