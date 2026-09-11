"""
Task 12 — Batch generation for the RAG vs. baseline evaluation set.

Runs every (repo, question) pair through both systems and writes results
incrementally to devpulse_evaluation_batch.json, so the run is safe to
resume if interrupted. This file is the input to manual_evaluation.py.
"""

import os
import time
import json
from google.genai import types
from google.genai.errors import APIError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from gemini_client import get_client
from rag_pipeline import retrieve_code_chunks, build_context_string

client = get_client()


@retry(
    retry=retry_if_exception_type(APIError),
    wait=wait_exponential(multiplier=2, min=5, max=90),
    stop=stop_after_attempt(6)
)
def generate_response(prompt: str, config: types.GenerateContentConfig) -> str:
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=config
    )
    time.sleep(4)  # pacing for free-tier quotas

    if response.candidates and response.candidates[0].finish_reason.name != "STOP":
        return f"[DEBUG] Generation halted. Reason: {response.candidates[0].finish_reason.name}"
    return response.text if response.text else "[DEBUG] Empty response."


def run_rag(question: str, collection_name: str) -> tuple[str, list[dict]]:
    chunks = retrieve_code_chunks(question, collection_name=collection_name)
    system_instruction = (
        "You are an expert developer assistant analyzing a codebase. Answer ONLY using the "
        "provided code context. Cite file paths and targets. If unknown, state: "
        "'I cannot answer this based on the provided context.'"
    )
    config = types.GenerateContentConfig(temperature=0.1, system_instruction=system_instruction)
    answer = generate_response(f"Context:\n{build_context_string(chunks)}\n\nQuestion: {question}", config)
    return answer, chunks


def run_baseline(question: str, repo_name: str) -> str:
    system_instruction = (
        f"You are a coding assistant. A developer is asking about the '{repo_name}' repository. "
        f"Answer using your own knowledge. Do not ask for the codebase."
    )
    config = types.GenerateContentConfig(
        temperature=0.1,
        system_instruction=system_instruction,
        tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="NONE"))
    )
    return generate_response(f"Question: {question}", config)


def run_evaluation_batch(repo_questions: dict, output_path: str = "devpulse_evaluation_batch.json"):
    results = []
    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            results = json.load(f)

    completed_trials = {r['trial_id'] for r in results}

    total_repos = len(repo_questions)
    for repo_idx, (repo, questions) in enumerate(repo_questions.items(), 1):
        collection_name = f"devpulse_{repo}"

        for q_idx, q_text in enumerate(questions, 1):
            q_id = f"q{q_idx:02d}"

            baseline_trial = f"{repo}_{q_id}_baseline"
            if baseline_trial not in completed_trials:
                print(f"Repo {repo_idx}/{total_repos} ({repo}) | Q {q_idx}/{len(questions)} | System: BASELINE")
                ans_base = run_baseline(q_text, repo)
                results.append({
                    "trial_id": baseline_trial, "repo": repo, "question_id": q_id,
                    "question_text": q_text, "system": "baseline", "answer_text": ans_base, "sources": []
                })
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2)

            rag_trial = f"{repo}_{q_id}_rag"
            if rag_trial not in completed_trials:
                print(f"Repo {repo_idx}/{total_repos} ({repo}) | Q {q_idx}/{len(questions)} | System: RAG")
                ans_rag, chunks = run_rag(q_text, collection_name)
                sources = [
                    {
                        "file_path": c['metadata'].get('file_path'),
                        "function_name": c['metadata'].get('function_name'),
                        "class_name": c['metadata'].get('class_name'),
                        "start_line": c['metadata'].get('start_line'),
                        "end_line": c['metadata'].get('end_line'),
                    }
                    for c in chunks
                ]

                results.append({
                    "trial_id": rag_trial, "repo": repo, "question_id": q_id,
                    "question_text": q_text, "system": "rag", "answer_text": ans_rag, "sources": sources
                })
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2)

    print("\nBatch generation complete!")


if __name__ == "__main__":
    my_test_questions = {
        "httpx": [
            "How does retry logic work in httpx?",
            "What does the Response class do?",
            "Where is authentication handled?",
            "How does httpx handle HTTP/2 connections?",
            "What's the purpose of the Client class vs the module-level get()/post() functions?",
            "How are cookies managed across requests?",
            "What happens when a request times out?",
            "How does httpx decide whether to follow redirects?",
            "What's the difference between content, text, and json() on a Response?",
            "How is streaming response content implemented?",
            "Where is proxy support configured?",
            "How does httpx validate or construct URLs?"
        ],
        "flask": [
            "How does Flask route a URL to a view function?",
            "What does the Blueprint class do?",
            "How is the application context (current_app) implemented?",
            "Where is session management handled?",
            "How does Flask's request context work?",
            "What happens when render_template() is called?",
            "How are error handlers (like 404) registered and triggered?",
            "What's the purpose of the g object?",
            "How does Flask decide which config values to load on startup?",
            "Where is the development server (app.run()) implemented?",
            "How do Flask extensions typically hook into the app?",
            "What does the before_request/after_request hook system do internally?"
        ],
        "algorithms": [
            "How is quicksort implemented in this repository?",
            "What data structures are implemented for a binary search tree?",
            "How does the merge sort implementation handle splitting the list?",
            "What's the time complexity documented (if any) for the implementations in the sorts folder?",
            "How is a linked list node represented in this codebase?",
            "What does the graph traversal (BFS/DFS) implementation look like?",
            "How are duplicate values handled in the sorting algorithms here?",
            "What testing pattern do these algorithm files follow, if any?",
            "How is recursion depth or base-case handled in the recursive sorting algorithms?",
            "What naming conventions are used across the algorithm files?",
            "How does the heap implementation maintain the heap property?",
            "Are there any type hints or docstrings consistently used across this folder?"
        ]
    }

    run_evaluation_batch(my_test_questions, "devpulse_evaluation_batch.json")
