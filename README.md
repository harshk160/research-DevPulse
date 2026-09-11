# DevPulse

**A Retrieval-Augmented Framework for Grounded Codebase Onboarding Assistance**

This repository is the data/code availability companion for the DevPulse research
paper. DevPulse is a RAG (Retrieval-Augmented Generation) pipeline that answers
developer questions about an unfamiliar codebase by grounding Gemini's answers
in retrieved code chunks (rather than the model's own unaided knowledge), and
compares that "grounded" system against a plain ungrounded baseline on
correctness and hallucination rate. It also computes a per-function "confusion
score" (complexity + query frequency + missing docs) to flag onboarding pain
points.

## Pipeline overview

```
repo URL ──▶ ingest.py ──▶ *_extracted.json ──▶ build_vector_db.py ──▶ ChromaDB
                                   │                                       │
                                   │                                       ▼
                                   │                              rag_pipeline.py
                                   │                             (RAG + baseline answers)
                                   ▼                                       │
                          confusion_scoring.py                            ▼
                          (complexity/query-hit                 run_batch_eval.py
                           confusion scores)                   (batch-generate answers
                                                                  for the full test set)
                                                                            │
                                                                            ▼
                                                                manual_evaluation.py
                                                              (blind human scoring →
                                                               evaluation_scores.csv)
```

## Repository structure

```
devpulse/
├── README.md
├── requirements.txt
├── src/
│   ├── gemini_client.py       # shared Gemini API-key/client helper
│   ├── ingest.py               # Task 6 — repo ingestion + Tree-sitter parsing
│   ├── build_vector_db.py      # Task 7 — embedding + ChromaDB pipeline
│   ├── rag_pipeline.py         # Task 8 — RAG retrieval + generation (+ baseline)
│   ├── confusion_scoring.py    # Task 9 — complexity/confusion scoring
│   ├── manual_evaluation.py    # Task 11 — blind manual scoring CLI
│   ├── run_batch_eval.py       # Task 12 — batch-generate RAG vs. baseline answers
│   └── token_audit.py          # utility — embedding token-budget sanity check
└── data/
    ├── extracted/               # devpulse_<repo>_extracted.json (Task 6 output)
    ├── query_log.json           # retrieval hit counts (Task 9 input/output)
    └── evaluation/
        ├── devpulse_evaluation_batch.json   # Task 12 output — raw model answers
        └── evaluation_scores.csv            # Task 13 output — human rubric scores
```

The `chroma_data/` vector database is **not** committed (it's a large binary
index, regenerable from `data/extracted/` in a few minutes — see below).
It's excluded via `.gitignore`.

## Repositories evaluated

- [`encode/httpx`](https://github.com/encode/httpx)
- [`pallets/flask`](https://github.com/pallets/flask)
- [`TheAlgorithms/Python`](https://github.com/TheAlgorithms/Python) (`sorts/` and `data_structures/` only)

## Setup

```bash
git clone <this-repo-url>
cd devpulse
pip install -r requirements.txt
```

You'll need a [Gemini API key](https://ai.google.dev/). Set it as an
environment variable:

```bash
export GEMINI_API_KEY="your-key-here"
```

(All scripts also work unmodified in Google Colab — `gemini_client.py` will
fall back to a Colab secret named `GEMINI_API_KEY` if the environment
variable isn't set.)

## Reproducing the pipeline

Run from inside `src/`:

```bash
# 1. Parse the target repos into structured JSON chunks
python ingest.py

# 2. Embed the chunks and build the ChromaDB collections
python build_vector_db.py

# 3. Sanity-check embedding token budgets (optional)
python token_audit.py

# 4. Try the RAG pipeline / ungrounded baseline interactively
python rag_pipeline.py

# 5. Compute per-function confusion scores
python confusion_scoring.py

# 6. Batch-generate RAG + baseline answers for the full evaluation set
python run_batch_eval.py

# 7. Manually score the batch output (blind A/B, console-based)
python manual_evaluation.py
```

Each stage writes its output as a JSON/CSV file in the working directory —
see `data/` for the versions used in the paper.

## Data availability

The `data/` folder contains the exact intermediate artifacts referenced in
the paper's Results section: extracted code chunks, the retrieval query log,
the raw batch-generated answers, and the final human evaluation scores. The
underlying source code for the three evaluated repositories is not
redistributed here — it's pulled live from GitHub by `ingest.py`.

## Citation

If you use this code or data, please cite the paper (citation to be added
once published).
