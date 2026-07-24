from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from queue_manager import jobs
import worker
import os
from llm import llm
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
import psutil
from langchain_community.document_loaders import PyPDFLoader

from chunking.recursive import get_chunks
from vectordb.faiss_store import (
    create_or_update_vector_store,
    get_vector_store
)
import uuid

from queue_manager import (
    document_queue,
    jobs
)

app = FastAPI(title="RAG Knowledge Assistant")
app.mount("/static", StaticFiles(directory="static"), name="static")
DOCUMENTS_DIR = "documents"

os.makedirs(DOCUMENTS_DIR, exist_ok=True)
from threading import Thread

from worker import process_documents

Thread(
    target=process_documents,
    daemon=True
).start()

class QuestionRequest(BaseModel):
    question: str


@app.get("/")
def health():
    return {
        "status": "running"
    }

@app.get("/ui")
async def ui():
    return FileResponse("static/index.html")

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...)
):
    file_path = os.path.join(
        DOCUMENTS_DIR,
        file.filename
    )

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "status": "queued",
        "filename": file.filename
    }

    document_queue.put(
        (
            job_id,
            file_path
        )
    )

    return {
        "message": "File uploaded",
        "job_id": job_id,
        "status": "queued"
    }

from llm import llm

@app.post("/ask")
def ask_question(request: QuestionRequest):
    available_mb = (
        psutil.virtual_memory().available
        / 1024 / 1024
    )

    if available_mb < 150:

        return {
            "status": "busy",
            "message": "Server is processing documents. Please try again later."
        }

    
    db = get_vector_store()
    docs = db.max_marginal_relevance_search(
    	request.question,
    	k=5,
    	fetch_k=20
	)
    context_parts = []

    for i, doc in enumerate(docs):

       context_parts.append(
          f"""
              CHUNK {i+1}

              SOURCE:
                 {doc.metadata.get("source")}

              CONTENT:
                 {doc.page_content}
          """
    )

    context = "\n\n".join(context_parts)
    
    prompt = f"""
You are a document QA assistant.

Rules:

1. Use only the provided chunks.
2. Pay attention to SOURCE.
3. Never mix information from different sources.
4. If multiple people appear, answer only about the relevant person.
5. If unsure, say:
   I could not find that information in the uploaded documents.

Context:

{context}

Question:
{request.question}
"""
    response = llm.invoke(prompt)
    return {
    "question": request.question,
    "answer": response.content,
    "chunks": [
        {
            "source": doc.metadata.get("source"),
            "content": doc.page_content[:1000]
        }
        for doc in docs
    ]
    }

    return {
        "answer": response.content,
        "sources": [
            {
                "source": doc.metadata.get("source"),
                "page": doc.metadata.get("page")
            }
            for doc in docs
        ]
    }

@app.get("/job/{job_id}")
def job_status(job_id: str):

    if job_id not in jobs:
        return {
            "error": "Job not found"
        }

    return jobs[job_id]
