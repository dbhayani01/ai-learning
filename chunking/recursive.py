from langchain_text_splitters import RecursiveCharacterTextSplitter


def get_chunks(documents):
    """
    Production-friendly recursive chunking for technical documents.
    Works well for:
    - AWS Docs
    - LangGraph Docs
    - FastAPI Docs
    - Interview Notes
    """

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )

    chunks = splitter.split_documents(documents)

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = i

    return chunks
