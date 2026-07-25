"""
RAG pipeline — retrieval, prompt construction, and answer generation.
"""
import re
from langchain_core.documents import Document
from app.llm import llm
from app.config import RETRIEVAL_K, RETRIEVAL_FETCH, NEAR_DUP_THRESHOLD
from vectordb.faiss_store import get_vector_store


# ── Question-type detection ────────────────────────────────────────────────────

_BIOGRAPHICAL_PATTERNS = re.compile(
    r"\b(who is|who are|tell me about|describe|introduce|background of|profile of"
    r"|what does .+ do|experience of|career of|about .+)\b",
    re.IGNORECASE,
)

_LIST_PATTERNS = re.compile(
    r"\b(list|what are|enumerate|give me all|skills|achievements|certifications"
    r"|qualifications|projects|responsibilities)\b",
    re.IGNORECASE,
)

_FACTUAL_PATTERNS = re.compile(
    r"\b(when|where|how many|how much|what year|which company|what is the)\b",
    re.IGNORECASE,
)


def _detect_question_type(question: str) -> str:
    """Returns 'biographical', 'list', or 'factual'."""
    if _BIOGRAPHICAL_PATTERNS.search(question):
        return "biographical"
    if _LIST_PATTERNS.search(question):
        return "list"
    return "factual"


# ── Near-duplicate filter ────────────────────────────────────────────────

def _word_set(text: str) -> set[str]:
    """Lowercase word tokens, strip punctuation."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _filter_near_duplicates(
    docs: list[Document],
    threshold: float = NEAR_DUP_THRESHOLD,
) -> list[Document]:
    """
    Remove chunks whose word content is largely a subset of an already-kept chunk.

    This fixes the 'education table snowball' problem:
      chunk-5  (1 row)  → kept
      chunk-6  (2 rows) → 85%+ words already in chunk-5  → DROPPED
      chunk-7  (3 rows) → 85%+ words already in chunk-5  → DROPPED
      ...and so on

    Algorithm:
      Per (source, page) key, maintain a running union of seen word tokens.
      Drop a chunk if >= threshold fraction of its own words are already seen.

    Args:
        docs:      MMR-ranked Documents (best first).
        threshold: Word-overlap fraction above which a chunk is a near-duplicate.

    Returns:
        Filtered list — unique, diverse chunks only.
    """
    seen: dict[str, set[str]] = {}  # key = "source||page"
    kept: list[Document] = []

    for doc in docs:
        source = doc.metadata.get("source", "")
        page   = str(doc.metadata.get("page", ""))
        key    = f"{source}||{page}"
        words  = _word_set(doc.page_content)

        if not words:
            continue

        if key not in seen:
            seen[key] = set(words)
            kept.append(doc)
            continue

        overlap = len(words & seen[key]) / len(words)
        if overlap < threshold:
            # Enough new content — keep it and add its words to seen
            seen[key] |= words
            kept.append(doc)
        # else: near-duplicate — silently drop

    return kept


# ── Prompt templates ───────────────────────────────────────────────────────────

_BASE_RULES = """\
You are a precise document Q&A assistant. Answer using ONLY the provided chunks.

RULES:
1. Carefully analyze each of the provided chunks to see which one contains the correct answer.
2. BIFURCATE and strictly base your final answer ONLY on the single chunk that accurately addresses the question. Ignore conflicting or irrelevant chunks.
3. If the answer is not in the chunks, say: "I could not find that information in the uploaded documents."
4. Do NOT mix information from unrelated chunks or unrelated people/topics.
5. CHAIN OF THOUGHT: You MUST start your response with <thinking> tags where you explicitly reason about which chunk contains the answer and why. End your reasoning with </thinking>. Then write your final answer after the tags.
6. Do NOT mention the chunk number or the source filename in your final answer. The system handles that automatically."""

_BIOGRAPHICAL_INSTRUCTION = """\
ANSWER FORMAT — BIOGRAPHICAL:
Write a clear, flowing 2-4 sentence paragraph that introduces the person: who they are,
their professional role/background, key expertise, and notable achievements.
After the paragraph, optionally add a SHORT bullet list of their top 3-5 skills or highlights.
Do NOT dump a raw list of 20+ items. Synthesize. Be human-readable."""

_LIST_INSTRUCTION = """\
ANSWER FORMAT — LIST:
Provide a clean, organized list. Group related items under sub-headings if helpful.
Keep it focused — include only what's relevant to the question."""

_FACTUAL_INSTRUCTION = """\
ANSWER FORMAT — FACTUAL:
Answer directly and concisely in 1-3 sentences. Include the specific fact asked for."""

_CONTEXT_TEMPLATE = """\
--- CHUNK {idx} ---
SOURCE: {source}  |  Page: {page}
CONTENT:
{content}
"""


def _format_context(docs: list[Document]) -> str:
    import os
    parts = []
    for i, doc in enumerate(docs, 1):
        source_path = doc.metadata.get("source", "unknown")
        safe_source = os.path.basename(source_path) if source_path != "unknown" else "unknown"
        parts.append(_CONTEXT_TEMPLATE.format(
            idx     = i,
            source  = safe_source,
            page    = doc.metadata.get("page", "N/A"),
            content = doc.page_content.strip(),
        ))
    return "\n\n".join(parts)


from langchain_core.messages import SystemMessage, HumanMessage

def _build_messages(question: str, context: str, session_id: str) -> list:
    """Construct the system prompt and conversation history."""
    q_type = _detect_question_type(question)

    if q_type == "biographical":
        format_instruction = _BIOGRAPHICAL_INSTRUCTION
    elif q_type == "list":
        format_instruction = _LIST_INSTRUCTION
    else:
        format_instruction = _FACTUAL_INSTRUCTION

    system_prompt = f"{_BASE_RULES}\n\n{format_instruction}"
    
    from langchain_core.messages import AIMessage
    
    msgs = [SystemMessage(content=system_prompt)]
    
    # Inject chat history if available
    from app.services.history import get_history
    if session_id:
        history_records = get_history(session_id)
        for record in history_records:
            if record["role"] == "user":
                msgs.append(HumanMessage(content=record["content"]))
            elif record["role"] == "ai":
                msgs.append(AIMessage(content=record["content"]))
                
    human_prompt = f"""Here are the retrieved document chunks:

<chunks>
{context}
</chunks>

QUESTION: {question}"""

    msgs.append(HumanMessage(content=human_prompt))
    return msgs


# ── Public API ─────────────────────────────────────────────────────────────────

import json

def answer_question_stream(question: str, user_id: int, session_id: str):
    """
    Run the full RAG pipeline and yield SSE-formatted strings.
    """
    try:
        db = get_vector_store(user_id)
    except FileNotFoundError:
        yield f"data: {json.dumps({'type': 'error', 'content': 'No document found. Please upload a PDF first.'})}\n\n"
        return

    # MMR: fetch_k candidates → re-rank to top k for diversity
    raw_docs = db.max_marginal_relevance_search(
        question,
        k=RETRIEVAL_K,
        fetch_k=RETRIEVAL_FETCH,
        lambda_mult=0.7,
    )

    # Post-retrieval near-duplicate filter
    docs = _filter_near_duplicates(raw_docs)

    if not docs:
        yield f"data: {json.dumps({'type': 'error', 'content': 'I could not find that information in the uploaded documents.'})}\n\n"
        return

    # Only format the top 3 chunks for the LLM context, but send all chunks to the UI
    context      = _format_context(docs[:3])
    q_type       = _detect_question_type(question)
    messages     = _build_messages(question, context, session_id)

    chunks_list = [
        {
            "source":   doc.metadata.get("source", "unknown"),
            "page":     doc.metadata.get("page", "N/A"),
            "chunk_id": doc.metadata.get("chunk_id", -1),
            "strategy": doc.metadata.get("chunk_strategy", "recursive"),
            "preview":  doc.page_content[:400],
        }
        for doc in docs
    ]
    
    # Extract metadata for history
    rag_meta = [{"source": c["source"], "chunk_id": c["chunk_id"]} for c in chunks_list[:3]]

    # Send session ID and metadata first
    yield f"data: {json.dumps({'type': 'session_id', 'session_id': session_id})}\n\n"
    yield f"data: {json.dumps({'type': 'metadata', 'question_type': q_type, 'chunks': chunks_list})}\n\n"

    # Stream LLM tokens (filter out the thinking block)
    final_ai_answer = ""
    buffer = ""
    post_thinking = False
    
    for chunk in llm.stream(messages):
        if chunk.content:
            if not post_thinking:
                buffer += chunk.content
                if "</thinking>" in buffer:
                    post_thinking = True
                    remainder = buffer.split("</thinking>")[-1].lstrip()
                    if remainder:
                        final_ai_answer += remainder
                        yield f"data: {json.dumps({'type': 'token', 'content': remainder})}\n\n"
            else:
                final_ai_answer += chunk.content
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
                
    # Fallback: if the model completely ignored the <thinking> instructions, yield the buffer
    if not post_thinking and buffer:
        # We can optionally strip out an opening <thinking> if it exists but wasn't closed
        import re
        clean_buffer = re.sub(r'<thinking>.*', '', buffer, flags=re.DOTALL).strip()
        if not clean_buffer:
            clean_buffer = buffer # If it was entirely unclosed thinking, just dump it
            
        final_ai_answer = clean_buffer
        yield f"data: {json.dumps({'type': 'token', 'content': clean_buffer})}\n\n"

    # Save to history
    if final_ai_answer:
        from app.services.history import add_message
        add_message(session_id, "user", question)
        add_message(session_id, "ai", final_ai_answer, rag_meta)
