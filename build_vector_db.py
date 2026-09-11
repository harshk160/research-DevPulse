"""
Task 7 — Embedding + ChromaDB pipeline.

Reads a *_extracted.json file produced by ingest.py, formats each chunk into
a token-budgeted text block, embeds it with Gemini, and upserts it into a
persistent ChromaDB collection. Re-runnable: chunks already present in the
collection are skipped rather than re-embedded.
"""

import json
import time
import hashlib
import chromadb
from google.genai import types
from google.genai.errors import APIError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from gemini_client import get_client

client = get_client()


@retry(
    retry=retry_if_exception_type(APIError),
    wait=wait_exponential(multiplier=2, min=5, max=70),
    stop=stop_after_attempt(7)
)
def get_embeddings_with_retry(texts: list[str], task_type: str) -> list[list[float]]:
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type)
    )
    return [emb.values for emb in response.embeddings]


def format_and_truncate(chunk: dict, max_tokens: int = 500) -> str:
    header = f"File: {chunk.get('file_path')} | Class: {chunk.get('class_name') or 'None'} | Function: {chunk.get('function_name') or 'None'}"
    docstring = chunk.get('docstring') or ''
    class_summary = chunk.get('class_summary') or ''
    source = chunk.get('source_text') or ''

    base_text = f"{header}\n{docstring}\n{class_summary}\n"
    base_tokens = int(len(base_text.split()) * 1.3)
    source_tokens = int(len(source.split()) * 1.3) if source else 0

    if base_tokens + source_tokens > max_tokens:
        if base_tokens > max_tokens:
            allowed_words = int(max_tokens / 1.3)
            return " ".join(base_text.split()[:allowed_words]) + "\n...[TRUNCATED]"
        else:
            allowed_source_tokens = max_tokens - base_tokens
            allowed_words = int(allowed_source_tokens / 1.3)
            truncated_source = " ".join(source.split()[:allowed_words]) + "\n...[TRUNCATED]"
            return f"{base_text}{truncated_source}"

    return f"{base_text}{source}"


def build_vector_db(json_path: str, collection_name: str, db_path: str = "./chroma_data", batch_size: int = 25):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    db_client = chromadb.PersistentClient(path=db_path)
    collection = db_client.get_or_create_collection(name=collection_name)

    print(f"Loaded {len(data)} chunks from {json_path}. Filtering and embedding...")

    # Fetch existing IDs from ChromaDB to avoid re-embedding
    existing_data = collection.get()
    existing_ids = set(existing_data['ids']) if existing_data and existing_data['ids'] else set()
    print(f"Found {len(existing_ids)} chunks already in collection. Skipping those...")

    start_time = time.time()
    filtered_count = 0
    processed_count = 0
    skipped_count = 0

    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]

        texts = []
        ids = []
        metadatas = []

        for chunk in batch:
            docstring = chunk.get('docstring') or ''
            source = chunk.get('source_text') or ''
            summary = chunk.get('class_summary') or ''

            if not docstring.strip() and not source.strip() and not summary.strip():
                filtered_count += 1
                continue

            id_string = f"{chunk['file_path']}_{chunk['function_name']}_{chunk['start_line']}"
            chunk_id = hashlib.md5(id_string.encode()).hexdigest()

            if chunk_id in existing_ids:
                skipped_count += 1
                continue

            formatted_text = format_and_truncate(chunk)
            texts.append(formatted_text)
            ids.append(chunk_id)

            meta = {k: v for k, v in chunk.items() if v is not None and k not in ('source_text', 'docstring', 'imports', 'class_summary')}
            metadatas.append(meta)

        if not texts:
            continue

        embeddings = get_embeddings_with_retry(texts, task_type="RETRIEVAL_DOCUMENT")
        collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

        processed_count += len(texts)
        print(f"Processed batch... (New chunks embedded: {processed_count} | Skipped: {skipped_count})")
        time.sleep(5)

    print(f"Filtered out {filtered_count} blank chunks. Skipped {skipped_count} existing chunks.")
    print(f"Finished embedding {processed_count} new chunks in {time.time() - start_time:.2f} seconds.")


def test_search(query: str, collection_name: str, db_path: str = "./chroma_data"):
    db_client = chromadb.PersistentClient(path=db_path)
    collection = db_client.get_collection(name=collection_name)

    query_embedding = get_embeddings_with_retry([query], task_type="RETRIEVAL_QUERY")[0]
    results = collection.query(query_embeddings=[query_embedding], n_results=5)

    print(f"\nTop 5 results for: '{query}'")
    for i in range(len(results['ids'][0])):
        meta = results['metadatas'][0][i]
        dist = results['distances'][0][i]
        print(f"[{i+1}] Distance: {dist:.4f} | File: {meta.get('file_path')} | Func: {meta.get('function_name')}")


if __name__ == "__main__":
    build_vector_db("devpulse_httpx_extracted.json", "devpulse_httpx")
    build_vector_db("devpulse_flask_extracted.json", "devpulse_flask")
    build_vector_db("devpulse_algorithms_extracted.json", "devpulse_algorithms")
