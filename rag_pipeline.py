"""
Task 8 — RAG retrieval + Gemini generation pipeline.

Given a natural-language question, retrieves the top-k relevant code chunks
from ChromaDB and asks Gemini to answer using only that context (the
"grounded"/RAG system). Also provides an ungrounded baseline that answers
from the model's own knowledge, for comparison.
"""

import time
import chromadb
from google.genai import types
from google.genai.errors import APIError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from gemini_client import get_client

client = get_client()


# 1. RETRIEVAL
@retry(
    retry=retry_if_exception_type(APIError),
    wait=wait_exponential(multiplier=2, min=5, max=70),
    stop=stop_after_attempt(7)
)
def embed_query(query: str) -> list[float]:
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=[query],
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
    )
    return response.embeddings[0].values


def retrieve_code_chunks(query: str, collection_name: str = "devpulse_chunks", db_path: str = "./chroma_data", k: int = 10) -> list[dict]:
    db_client = chromadb.PersistentClient(path=db_path)
    collection = db_client.get_collection(name=collection_name)
    query_vector = embed_query(query)
    results = collection.query(query_embeddings=[query_vector], n_results=k)

    chunks = []
    if not results['ids']:
        return chunks

    for i in range(len(results['ids'][0])):
        chunks.append({
            "id": results['ids'][0][i],
            "document": results['documents'][0][i],
            "metadata": results['metadatas'][0][i],
            "distance": results['distances'][0][i]
        })
    return chunks


# 2. PROMPT BUILDING
def build_context_string(chunks: list[dict]) -> str:
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk['metadata']
        file_path = meta.get('file_path', 'Unknown')
        func_name = meta.get('function_name') or meta.get('class_name', 'None')
        start_line = meta.get('start_line', '?')
        end_line = meta.get('end_line', '?')
        doc = chunk['document']

        context_parts.append(
            f"--- CHUNK {i} ---\n"
            f"Source: {file_path} | Target: {func_name} | Lines: {start_line}-{end_line}\n"
            f"{doc}\n"
        )
    return "\n".join(context_parts)


# 3. GENERATION
@retry(
    retry=retry_if_exception_type(APIError),
    wait=wait_exponential(multiplier=2, min=5, max=70),
    stop=stop_after_attempt(7)
)
def generate_response(prompt: str, system_instruction: str, model_name: str = "gemini-3.6-flash") -> str:
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.1
        )
    )

    if response.candidates:
        candidate = response.candidates[0]
        if candidate.finish_reason.name != "STOP":
            safety_info = [f"{s.category.name}: {s.probability.name}" for s in candidate.safety_ratings] if candidate.safety_ratings else "None"
            return f"[DEBUG] Generation halted. Reason: {candidate.finish_reason.name} | Safety: {safety_info}"

    if not response.text:
        return f"[DEBUG] Empty response. Feedback: {getattr(response, 'prompt_feedback', 'None')}"

    return response.text


# 4. PIPELINE ORCHESTRATION
def answer_question(question: str, collection_name: str = "devpulse_chunks", k: int = 10) -> tuple[str, list[dict]]:
    chunks = retrieve_code_chunks(question, collection_name=collection_name, k=k)
    context_str = build_context_string(chunks)

    system_instruction = (
        "You are an expert developer assistant analyzing a codebase. "
        "You must answer the user's question ONLY using the provided code context. "
        "Always cite the file path and function/class name for any claim you make. "
        "If the answer cannot be determined from the provided context, state explicitly: "
        "'I cannot answer this based on the provided context.' Do not guess or use outside knowledge."
    )

    prompt = f"Context:\n{context_str}\n\nQuestion: {question}"
    answer = generate_response(prompt, system_instruction)
    return answer, chunks


@retry(
    retry=retry_if_exception_type(APIError),
    wait=wait_exponential(multiplier=2, min=5, max=70),
    stop=stop_after_attempt(7)
)
def answer_question_baseline(question: str, repo_name: str) -> tuple[str, list]:
    system_instruction = (
        f"You are a helpful coding assistant. A developer is asking a question about the open-source repository '{repo_name}'. "
        f"Answer as best you can using your own knowledge of this library. Do not ask the user to provide, attach, or paste the codebase — "
        f"just answer directly based on what you know, even if you're not fully certain."
    )
    prompt = f"Question: {question}"

    # Explicitly block autonomous tool execution
    config = types.GenerateContentConfig(
        temperature=0.1,
        system_instruction=system_instruction,
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="NONE")
        )
    )

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=config
    )

    if response.candidates:
        candidate = response.candidates[0]
        if candidate.finish_reason.name != "STOP":
            safety_info = [f"{s.category.name}: {s.probability.name}" for s in candidate.safety_ratings] if candidate.safety_ratings else "None"
            return f"[DEBUG] Generation halted. Reason: {candidate.finish_reason.name} | Safety: {safety_info}", []

    if not response.text:
        return f"[DEBUG] Empty response. Feedback: {getattr(response, 'prompt_feedback', 'None')}", []

    return response.text, []


def debug_retrieved_chunks(query: str, collection_name: str = "devpulse_chunks", db_path: str = "./chroma_data", k: int = 10):
    db_client = chromadb.PersistentClient(path=db_path)
    collection = db_client.get_collection(name=collection_name)

    query_vector = embed_query(query)
    results = collection.query(query_embeddings=[query_vector], n_results=k)

    print(f"\nRAW TEXT FOR QUERY: '{query}'\n" + "=" * 80)
    if not results['ids']:
        print("No chunks found.")
        return

    for i in range(len(results['ids'][0])):
        meta = results['metadatas'][0][i]
        text = results['documents'][0][i]
        print(f"\n[{i+1}] File: {meta.get('file_path')} | Target: {meta.get('function_name') or meta.get('class_name')}")
        print("-" * 80)
        print(text)
        print("-" * 80)


if __name__ == "__main__":
    questions = [
        "How does retry logic work in httpx?",
        "What does the Response class do?",
        "Where is authentication handled?"
    ]

    for q in questions:
        print(f"\n{'='*80}\nQUESTION: {q}\n{'='*80}")
        print("\n[DEBUG - RETRIEVED CHUNKS]")
        debug_retrieved_chunks(q, collection_name="devpulse_httpx", k=10)

        print("\n[BASELINE - UNGROUNDED]")
        baseline_ans, _ = answer_question_baseline(q, repo_name="httpx")
        print(baseline_ans)

        time.sleep(5)

        print("\n[RAG - DEVPULSE GROUNDED]")
        rag_ans, sources = answer_question(q, collection_name="devpulse_httpx", k=10)
        print(rag_ans)

        print("\n[SOURCES RETRIEVED]")
        for s in sources:
            meta = s['metadata']
            print(f"- {meta.get('file_path')} (Line {meta.get('start_line')})")

        time.sleep(5)
