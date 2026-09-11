"""
Utility — checks how many chunks in each *_extracted.json would exceed the
embedding token budget (max_tokens) once formatted, for module-doc / empty-
source chunks specifically. Useful sanity check before running build_vector_db.py.
"""

import json


def audit_token_budget(json_paths: list[str], max_tokens: int = 500):
    for path in json_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            continue

        oversized = []
        for chunk in data:
            docstring = chunk.get('docstring') or ''
            class_summary = chunk.get('class_summary') or ''
            source = chunk.get('source_text') or ''

            base_text = f"{docstring}\n{class_summary}\n"
            base_tokens = int(len(base_text.split()) * 1.3)
            source_tokens = int(len(source.split()) * 1.3) if source else 0
            total_tokens = base_tokens + source_tokens

            if (chunk.get('chunk_type') == 'module_doc' or not source) and total_tokens > max_tokens:
                oversized.append(chunk)

        print(f"[{path}] Oversized Chunks (Before Fix): {len(oversized)}")
        if oversized:
            print("  Examples:")
            for c in oversized[:3]:
                text_len = len(f"{c.get('docstring') or ''} {c.get('class_summary') or ''}".split())
                print(f"  - File: {c.get('file_path')} | Class: {c.get('class_name')} | Estimated Tokens: ~{int(text_len * 1.3)}")
        print("-" * 60)


if __name__ == "__main__":
    audit_token_budget([
        "devpulse_httpx_extracted.json",
        "devpulse_flask_extracted.json",
        "devpulse_algorithms_extracted.json"
    ])
