from langchain_community.document_loaders import PyPDFLoader

loader = PyPDFLoader("documents/30084012_Dwarkesh_Bhayani.pdf")
docs = loader.load()

with open("pdf_out.txt", "w", encoding="utf-8") as f:
    for i, doc in enumerate(docs):
        f.write(f"--- PAGE {i} ---\n")
        f.write(doc.page_content)
        f.write("\n\n")
