"""
Vector store abstraction layer.
"""
from vectordb.faiss_store import create_or_update_vector_store, get_vector_store

__all__ = ["create_or_update_vector_store", "get_vector_store"]
