"""
LLM client — single shared instance.
"""
from langchain_groq import ChatGroq
from app.config import GROQ_API_KEY, LLM_MODEL

llm = ChatGroq(
    model=LLM_MODEL,
    api_key=GROQ_API_KEY,
    temperature=0.1,      # 0.1 prevents deterministic repetition loops
    max_retries=2,
)
