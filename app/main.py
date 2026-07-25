"""
RAG Knowledge Assistant — FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
import logging
from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import STATIC_DIR
from app.routes.upload import router as upload_router
from app.routes.query  import router as query_router
from app.routes.auth   import router as auth_router
from app.services.worker import process_documents

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan (replaces deprecated @app.on_event) ───────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch the background worker thread
    worker_thread = Thread(target=process_documents, daemon=True, name="doc-worker")
    worker_thread.start()
    logger.info("Background document worker started (thread: %s)", worker_thread.name)
    yield
    # Shutdown: daemon thread exits automatically with the process


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "RAG Knowledge Assistant",
    description = "Upload PDFs and ask questions — powered by FAISS + Groq LLaMA.",
    version     = "2.0.0",
    lifespan    = lifespan,
)

# Static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Routers
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(query_router)


# ── Root routes ────────────────────────────────────────────────────────────────
@app.get("/", tags=["health"], summary="Health check")
def health():
    return {"status": "running", "version": app.version}


@app.get("/ui", tags=["ui"], summary="Serve the web UI", include_in_schema=False)
async def ui():
    return FileResponse(f"{STATIC_DIR}/index.html")
