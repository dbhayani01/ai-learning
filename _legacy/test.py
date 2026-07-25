from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FastEmbedEmbeddings

embeddings = FastEmbedEmbeddings()

db = FAISS.load_local(
    "faiss_index",
    embeddings,
    allow_dangerous_deserialization=True
)

results = db.similarity_search(
    "What is LangGraph State?",
    k=3
)

for i, doc in enumerate(results, 1):
    print(f"\nResult {i}")
    print(doc.page_content[:500])
