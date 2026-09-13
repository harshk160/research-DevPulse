"""
Task 9 — Complexity/confusion scoring module.

Combines three signals per function into a single "confusion score" meant to
flag functions that are good candidates for onboarding attention:
  - cyclomatic complexity (structural)
  - query frequency (how often devs asked about it)
  - presence/absence of a docstring

confusion_score = (norm(complexity) + norm(log(1 + hits)) + no_docstring_penalty) / 3

Query hit counts are derived retroactively from the Task 12 batch-evaluation
output (devpulse_evaluation_batch.json): every source chunk a RAG answer
cited during that run counts as one "hit" against that function, split out
per repo. This reuses the same batch data used for the RAG-vs-baseline
evaluation instead of requiring a separate live query-logging session.

Running this script:
  - prints the top-10 highest-confusion functions per repo to the console
  - writes the complete ranked table for each repo to
    data/confusion_scores/confusion_scores_<repo>.txt
  - writes query_log_<repo>.json (hit counts by chunk id) per repo
"""

import os
import json
import math
import hashlib

REPOS = [
    ("httpx", "devpulse_httpx_extracted.json"),
    ("flask", "devpulse_flask_extracted.json"),
    ("algorithms", "devpulse_algorithms_extracted.json"),
]

TABLE_WIDTH = 145


# 1. QUERY LOG EXTRACTION
def extract_repo_query_logs(batch_json_path: str) -> dict[str, dict[str, int]]:
    """Extracts isolated query hit counts per repo from the Task 12 batch results."""
    with open(batch_json_path, 'r', encoding='utf-8') as f:
        batch_data = json.load(f)

    repo_logs = {"httpx": {}, "flask": {}, "algorithms": {}}

    for item in batch_data:
        if item.get("system") != "rag":
            continue
        repo = item.get("repo")
        if repo not in repo_logs:
            repo_logs[repo] = {}

        for src in item.get("sources", []):
            # Recreate the deterministic chunk ID hash used in build_vector_db.py
            id_string = f"{src['file_path']}_{src['function_name']}_{src['start_line']}"
            chunk_id = hashlib.md5(id_string.encode()).hexdigest()
            repo_logs[repo][chunk_id] = repo_logs[repo].get(chunk_id, 0) + 1

    for repo, log_data in repo_logs.items():
        with open(f"query_log_{repo}.json", 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=4)

    return repo_logs


# 2. SCORING
def normalize(value: float, min_val: float, max_val: float) -> float:
    """Min-Max normalization to [0, 1]."""
    if max_val == min_val:
        return 0.0
    return (value - min_val) / (max_val - min_val)


def compute_confusion_scores_for_repo(extraction_json_path: str, query_log: dict) -> tuple[list[dict], dict]:
    with open(extraction_json_path, 'r', encoding='utf-8') as f:
        all_chunks = json.load(f)

    functions = [c for c in all_chunks if c.get('chunk_type') == 'function']
    if not functions:
        return [], {"total_funcs": 0, "hit_funcs": 0, "coverage_pct": 0.0}

    scored_functions = []
    complexities = []
    query_logs = []
    hit_functions_count = 0

    for func in functions:
        id_string = f"{func['file_path']}_{func['function_name']}_{func['start_line']}"
        chunk_id = hashlib.md5(id_string.encode()).hexdigest()

        complexity = func.get('cyclomatic_complexity') or 1
        hits = query_log.get(chunk_id, 0)
        if hits > 0:
            hit_functions_count += 1

        log_hits = math.log(1 + hits)
        has_doc = 1 if func.get('docstring') else 0

        complexities.append(complexity)
        query_logs.append(log_hits)

        scored_functions.append({
            "file_path": func['file_path'],
            "function_name": func['function_name'],
            "class_name": func.get('class_name'),
            "start_line": func.get('start_line', '?'),
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

    stats = {
        "total_funcs": len(functions),
        "hit_funcs": hit_functions_count,
        "coverage_pct": (hit_functions_count / len(functions)) * 100
    }

    return sorted(scored_functions, key=lambda x: x['confusion_score'], reverse=True), stats


# 3. REPORTING
def format_report_lines(repo_name: str, scored_funcs: list[dict], stats: dict, limit: int | None = 10) -> list[str]:
    """Builds the ranked table as a list of text lines. limit=None -> full table."""
    title = "TOP 10 HIGHEST CONFUSION FUNCTIONS" if limit else "FULL CONFUSION SCORE RANKING"
    lines = [
        f"\n{'='*TABLE_WIDTH}",
        f"REPOSITORY: {repo_name.upper()} | {title}",
        f"{'='*TABLE_WIDTH}",
        f"{'Function':<28} | {'Class':<18} | {'File Path':<35} | {'Line':<5} | {'Comp':<4} | {'Hits':<4} | {'Doc?':<4} | {'Score':<6}",
        "-" * TABLE_WIDTH,
    ]

    rows = scored_funcs[:limit] if limit else scored_funcs
    for row in rows:
        func_name = (row['function_name'][:25] + "...") if len(row['function_name']) > 28 else row['function_name']
        class_name = str(row['class_name'])[:15] + "..." if row['class_name'] and len(row['class_name']) > 18 else str(row['class_name'])

        file_path = row['file_path']
        if len(file_path) > 35:
            file_path = "..." + file_path[-32:]

        line_no = row.get('start_line', '?')

        lines.append(
            f"{func_name:<28} | {class_name:<18} | {file_path:<35} | {line_no:<5} | "
            f"{row['raw_complexity']:<4} | {row['raw_hits']:<4} | {'Yes' if row['has_docstring'] else 'No':<4} | {row['confusion_score']:.4f}"
        )

    lines.append("-" * TABLE_WIDTH)
    lines.append(
        f"Query Signal Coverage: {stats['hit_funcs']}/{stats['total_funcs']} functions queried "
        f"({stats['coverage_pct']:.2f}% coverage; {100 - stats['coverage_pct']:.2f}% sparse)"
    )
    return lines


def print_repo_report(repo_name: str, scored_funcs: list[dict], stats: dict, limit: int | None = 10):
    print("\n".join(format_report_lines(repo_name, scored_funcs, stats, limit=limit)))


def save_full_report(repo_name: str, scored_funcs: list[dict], stats: dict, output_dir: str = "data/confusion_scores") -> str:
    """Writes the complete (non-truncated) ranked table for one repo to its own .txt file."""
    os.makedirs(output_dir, exist_ok=True)
    lines = format_report_lines(repo_name, scored_funcs, stats, limit=None)
    out_path = os.path.join(output_dir, f"confusion_scores_{repo_name}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved full confusion-score table for {repo_name} -> {out_path}")
    return out_path


if __name__ == "__main__":
    logs = extract_repo_query_logs("devpulse_evaluation_batch.json")

    for repo_name, extracted_path in REPOS:
        if not os.path.exists(extracted_path):
            continue

        scored, stats = compute_confusion_scores_for_repo(extracted_path, logs.get(repo_name, {}))

        # Console: top-10 summary (what goes in the paper)
        print_repo_report(repo_name, scored, stats, limit=10)

        # File: complete ranked table, one .txt per repo (data availability)
        save_full_report(repo_name, scored, stats)
