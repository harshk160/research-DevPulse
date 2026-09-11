"""
Task 9 — Complexity/confusion scoring module.

Combines three signals per function into a single "confusion score" meant to
flag functions that are good candidates for onboarding attention:
  - cyclomatic complexity (structural)
  - query frequency in query_log.json (how often devs asked about it)
  - presence/absence of a docstring

confusion_score = (norm(complexity) + norm(log(1 + hits)) + no_docstring_penalty) / 3
"""

import os
import json
import math
import hashlib

from rag_pipeline import retrieve_code_chunks


# 1. LOGGING
def log_query_hits(chunk_ids: list[str], log_path: str = "query_log.json"):
    """Persistently logs vector retrieval hits."""
    log_data = {}
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            log_data = json.load(f)

    for cid in chunk_ids:
        log_data[cid] = log_data.get(cid, 0) + 1

    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=4)


def retrieve_and_log(query: str, collection_name: str, db_path: str = "./chroma_data", k: int = 10, log_path: str = "query_log.json") -> list[dict]:
    """Thin wrapper around rag_pipeline.retrieve_code_chunks that also logs the hits."""
    chunks = retrieve_code_chunks(query, collection_name=collection_name, db_path=db_path, k=k)
    if chunks:
        log_query_hits([c["id"] for c in chunks], log_path=log_path)
    return chunks


# 2. SCORING
def normalize(value: float, min_val: float, max_val: float) -> float:
    """Min-Max normalization to [0, 1]."""
    if max_val == min_val:
        return 0.0
    return (value - min_val) / (max_val - min_val)


def compute_confusion_scores(extraction_json_path: str, query_log_path: str) -> list[dict]:
    with open(extraction_json_path, 'r', encoding='utf-8') as f:
        all_chunks = json.load(f)

    log_data = {}
    if os.path.exists(query_log_path):
        with open(query_log_path, 'r', encoding='utf-8') as f:
            log_data = json.load(f)

    functions = [c for c in all_chunks if c.get('chunk_type') == 'function']

    scored_functions = []
    complexities = []
    query_logs = []

    for func in functions:
        id_string = f"{func['file_path']}_{func['function_name']}_{func['start_line']}"
        chunk_id = hashlib.md5(id_string.encode()).hexdigest()

        complexity = func.get('cyclomatic_complexity') or 1
        hits = log_data.get(chunk_id, 0)
        log_hits = math.log(1 + hits)

        has_doc = 0 if not func.get('docstring') else 1

        complexities.append(complexity)
        query_logs.append(log_hits)

        scored_functions.append({
            "file_path": func['file_path'],
            "function_name": func['function_name'],
            "class_name": func.get('class_name'),
            "raw_complexity": complexity,
            "raw_hits": hits,
            "log_hits": log_hits,
            "has_docstring": has_doc
        })

    min_c, max_c = min(complexities), max(complexities)
    min_q, max_q = min(query_logs), max(query_logs)

    for sf in scored_functions:
        c_norm = normalize(sf['raw_complexity'], min_c, max_c)
        q_norm = normalize(sf['log_hits'], min_q, max_q)
        d_penalty = 1.0 if sf['has_docstring'] == 0 else 0.0

        sf['confusion_score'] = (c_norm + q_norm + d_penalty) / 3.0

    return sorted(scored_functions, key=lambda x: x['confusion_score'], reverse=True)


# 3. REPORTING
def print_table(title: str, data: list[dict], sort_key: str):
    print(f"\n{title}")
    print("-" * 125)
    print(f"{'Function':<30} | {'Class':<20} | {'Complexity':<10} | {'Hits':<5} | {'Doc?':<5} | {'Score':<6}")
    print("-" * 125)

    sorted_data = sorted(data, key=lambda x: x[sort_key], reverse=True)[:10]

    for row in sorted_data:
        func_name = (row['function_name'][:27] + "...") if len(row['function_name']) > 30 else row['function_name']
        class_name = str(row['class_name'])[:17] + "..." if row['class_name'] and len(row['class_name']) > 20 else str(row['class_name'])

        print(f"{func_name:<30} | {class_name:<20} | {row['raw_complexity']:<10} | {row['raw_hits']:<5} | {'Yes' if row['has_docstring'] else 'No':<5} | {row['confusion_score']:.4f}")


def print_confusion_reports(scored_functions: list[dict]):
    print_table("TOP 10 BY OVERALL CONFUSION SCORE", scored_functions, 'confusion_score')
    print_table("TOP 10 BY RAW COMPLEXITY ALONE", scored_functions, 'raw_complexity')
    print_table("TOP 10 BY RAW QUERY FREQUENCY ALONE", scored_functions, 'raw_hits')


if __name__ == "__main__":
    sample_queries = [
        "How do I create a synchronous httpx Client?",
        "What is the recommended way to stream large file downloads?",
        "How does httpx handle cookie persistence across redirects?",
        "Where is proxy configuration and routing handled?",
        "How do I configure read, write, and connect timeouts?",
        "How does the library manage maximum redirect loops?",
        "Where are event hooks executed for requests and responses?",
        "How does httpx handle SSL certificate verification?",
        "How do I implement and mount a custom BaseTransport?",
        "How are query parameters encoded into the final URL?"
    ]

    print("Running 10 queries to populate query_log.json...")
    for q in sample_queries:
        retrieve_and_log(q, collection_name="devpulse_httpx", k=10)
    print("Queries complete. Log updated.\n")

    scores = compute_confusion_scores("devpulse_httpx_extracted.json", "query_log.json")
    print_confusion_reports(scores)
