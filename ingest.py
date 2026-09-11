"""
Task 6 — Repository ingestion + Tree-sitter parsing.

Clones (or reads) a Python repository, walks its .py files, and parses each
one with Tree-sitter into a flat list of "chunks": module docstrings,
classes, and functions. Each chunk also gets a cyclomatic complexity score
(functions only) and, for classes without their own docstring, a synthesized
summary built from __init__'s docstring and method signatures.

Output: one JSON file per repo, e.g. devpulse_httpx_extracted.json
"""

import os
import json
import tempfile
import subprocess

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)

COMPLEXITY_NODES = {
    'if_statement', 'elif_clause', 'for_statement',
    'while_statement', 'except_clause', 'case_clause'
}

BANNED_DIRS = {'tests', 'venv', '.venv', '__pycache__', '.git', 'site-packages'}


def clone_or_get_path(source: str) -> tuple[str, tempfile.TemporaryDirectory | None]:
    """If `source` is a git URL, shallow-clone it to a temp dir and return that
    path plus the TemporaryDirectory handle (so the caller can clean it up).
    Otherwise treat `source` as an existing local path."""
    if source.startswith(("http://", "https://", "git@")):
        temp_dir = tempfile.TemporaryDirectory(prefix="devpulse_")
        print(f"Cloning {source} into {temp_dir.name}...")
        subprocess.run(["git", "clone", "--depth", "1", source, temp_dir.name], check=True, capture_output=True)
        return temp_dir.name, temp_dir
    return source, None


def walk_python_files(walk_root: str, project_root: str):
    for dirpath, dirnames, filenames in os.walk(walk_root):
        dirnames[:] = [d for d in dirnames if d not in BANNED_DIRS]
        for file in filenames:
            if file.endswith('.py') and not file.startswith('test_'):
                yield os.path.join(dirpath, file)


def calculate_cyclomatic_complexity(node, source_bytes: bytes) -> int:
    complexity = 1

    def walk(n):
        nonlocal complexity
        if n.type in COMPLEXITY_NODES:
            complexity += 1
        elif n.type == 'boolean_operator':
            operator_node = n.child_by_field_name('operator')
            if operator_node:
                op_text = source_bytes[operator_node.start_byte:operator_node.end_byte].decode('utf8')
                if op_text in ('and', 'or'):
                    complexity += 1
        for child in n.children:
            walk(child)

    walk(node)
    return complexity


def extract_docstring(node, source_bytes: bytes) -> str | None:
    body = node.child_by_field_name('body') if node.type != 'module' else node
    if not body:
        return None
    for child in body.children:
        if child.type == 'expression_statement' and child.children:
            if child.children[0].type == 'string':
                return source_bytes[child.start_byte:child.end_byte].decode('utf8').strip('''"'\t\n ''')
        elif child.type != 'comment':
            break
    return None


def extract_imports(node, source_bytes: bytes) -> list[str]:
    imports = []

    def walk(n):
        if n.type in ('import_statement', 'import_from_statement'):
            imports.append(source_bytes[n.start_byte:n.end_byte].decode('utf8'))
        for child in n.children:
            walk(child)

    walk(node)
    return imports


def enrich_class_chunks(chunks: list[dict]) -> list[dict]:
    """Synthesizes class summaries for classes lacking docstrings by extracting
    the __init__ docstring and a list of method signatures."""
    classes = [c for c in chunks if c['chunk_type'] == 'class']
    functions = [c for c in chunks if c['chunk_type'] == 'function']

    for cls in classes:
        if cls['docstring']:
            cls['class_summary'] = cls['docstring']
            continue

        class_methods = [f for f in functions if f['class_name'] == cls['class_name']]
        summary_parts = []

        init_method = next((m for m in class_methods if m['function_name'] == '__init__'), None)
        if init_method and init_method['docstring']:
            summary_parts.append(f"Initialization: {init_method['docstring']}")

        if class_methods:
            summary_parts.append("Methods:")
            for m in class_methods:
                m_name = m['function_name']
                m_doc = m['docstring']
                if m_doc:
                    first_line = m_doc.strip().split('\n')[0]
                    summary_parts.append(f"- {m_name}(): {first_line}")
                else:
                    summary_parts.append(f"- {m_name}()")
        else:
            summary_parts.append("Methods: None")

        cls['class_summary'] = "\n".join(summary_parts)

    for c in chunks:
        if c['chunk_type'] != 'class':
            c['class_summary'] = None

    return chunks


def parse_python_file(filepath: str, root_path: str) -> list[dict]:
    with open(filepath, 'rb') as f:
        source_bytes = f.read()

    tree = parser.parse(source_bytes)
    root_node = tree.root_node
    rel_path = os.path.relpath(filepath, root_path)
    chunks = []

    chunks.append({
        "chunk_type": "module_doc",
        "file_path": rel_path,
        "class_name": None,
        "function_name": None,
        "start_line": root_node.start_point[0] + 1,
        "end_line": root_node.end_point[0] + 1,
        "docstring": extract_docstring(root_node, source_bytes),
        "class_summary": None,
        "source_text": None,
        "cyclomatic_complexity": None,
        "imports": extract_imports(root_node, source_bytes)
    })

    def extract_entities(node, parent_class=None):
        for child in node.children:
            if child.type == 'class_definition':
                name_node = child.child_by_field_name('name')
                class_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')

                chunks.append({
                    "chunk_type": "class",
                    "file_path": rel_path,
                    "class_name": class_name,
                    "function_name": None,
                    "start_line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "docstring": extract_docstring(child, source_bytes),
                    "class_summary": None,  # populated during enrichment
                    "source_text": None,
                    "cyclomatic_complexity": None,
                    "imports": None
                })

                body = child.child_by_field_name('body')
                if body:
                    extract_entities(body, parent_class=class_name)

            elif child.type == 'function_definition':
                name_node = child.child_by_field_name('name')
                func_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')

                chunks.append({
                    "chunk_type": "function",
                    "file_path": rel_path,
                    "class_name": parent_class,
                    "function_name": func_name,
                    "start_line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "docstring": extract_docstring(child, source_bytes),
                    "class_summary": None,
                    "source_text": source_bytes[child.start_byte:child.end_byte].decode('utf8'),
                    "cyclomatic_complexity": calculate_cyclomatic_complexity(child, source_bytes),
                    "imports": None
                })

                body = child.child_by_field_name('body')
                if body:
                    extract_entities(body, parent_class=parent_class)
            else:
                extract_entities(child, parent_class)

    extract_entities(root_node)
    return enrich_class_chunks(chunks)


def dump_to_json(data: list[dict], output_path: str):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f"Exported {len(data)} chunks to {output_path}")


def process_repository(source: str, target_subfolders: list[str] = None) -> list[dict]:
    local_path, temp_ref = clone_or_get_path(source)
    all_chunks = []
    try:
        paths_to_walk = [os.path.join(local_path, sub) for sub in target_subfolders] if target_subfolders else [local_path]
        for path in paths_to_walk:
            if os.path.exists(path):
                for filepath in walk_python_files(path, project_root=local_path):
                    all_chunks.extend(parse_python_file(filepath, local_path))
    finally:
        if temp_ref:
            temp_ref.cleanup()
    return all_chunks


if __name__ == "__main__":
    repos = [
        {"name": "httpx", "url": "https://github.com/encode/httpx", "subfolders": None},
        {"name": "flask", "url": "https://github.com/pallets/flask", "subfolders": None},
        {"name": "algorithms", "url": "https://github.com/TheAlgorithms/Python", "subfolders": ["sorts", "data_structures"]}
    ]

    for repo in repos:
        print(f"\nProcessing {repo['name']}...")
        data = process_repository(repo['url'], target_subfolders=repo['subfolders'])
        dump_to_json(data, f"devpulse_{repo['name']}_extracted.json")
