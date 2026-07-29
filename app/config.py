"""
Centralized configuration — reads from .env and provides typed constants.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR   = str(BASE_DIR / "documents")
FAISS_INDEX_DIR = str(BASE_DIR / "faiss_index")
STATIC_DIR      = str(BASE_DIR / "static")

# ── LLM ────────────────────────────────────────────────────────────────────────
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
LLM_MODEL       = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
VISION_BOT_TOKEN= os.getenv("VISION_BOT_TOKEN", "")

# ── Chunking ───────────────────────────────────────────────────────────────────
CHUNK_STRATEGY  = os.getenv("CHUNK_STRATEGY", "recursive")   # recursive | semantic
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "100"))     # lower overlap prevents
                                                              # snowball on table rows

# ── Retrieval ──────────────────────────────────────────────────────────────────
RETRIEVAL_K          = int(os.getenv("RETRIEVAL_K", "6"))
RETRIEVAL_FETCH      = int(os.getenv("RETRIEVAL_FETCH", "30"))
# Post-retrieval near-duplicate filter: drop chunks where >N% of their words
# already appear in a higher-ranked chunk from the same source.
NEAR_DUP_THRESHOLD   = float(os.getenv("NEAR_DUP_THRESHOLD", "0.85"))

# ── Memory guard ───────────────────────────────────────────────────────────────
MIN_FREE_MB_QUERY  = int(os.getenv("MIN_FREE_MB_QUERY", "50"))
MIN_FREE_MB_WORKER = int(os.getenv("MIN_FREE_MB_WORKER", "100"))

# ── Ensure directories exist ───────────────────────────────────────────────────
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
