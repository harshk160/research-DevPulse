# DevPulse — Viva Preparation Summary

One document to revise from. Know the elevator pitch cold, then the rest falls into place.

---

## 1. The 30-second answer: "What is your project?"

> "New developers joining a codebase they didn't write spend most of their early time just understanding it, not contributing to it — one well-cited study found developers spend about 58% of their time on comprehension, not writing code. Existing AI tools like GitHub Copilot help you *write* code, and tools like Sourcegraph help you *search* code, but nothing gives a new developer a grounded, guided orientation to a specific, unfamiliar codebase. DevPulse is a RAG — retrieval-augmented generation — system that answers developer questions about a codebase using only that codebase's real structure, cites the exact file and function for every claim, and separately flags which parts of the code are most likely to confuse a newcomer. We built it, tested it on three real open-source Python projects, and found that it's 100% accurate with zero hallucinations, while a plain AI assistant without this grounding hallucinates badly — especially on the codebase it's least likely to already know from training."

---

## 2. How it works — plain-language walkthrough (say this if asked "explain the system")

Four steps, in order:

1. **Read the code's structure.** We give it a GitHub repo. A tool called Tree-sitter parses every Python file and pulls out every function, class, docstring, and import — like generating a table of contents for the entire codebase, plus a complexity score per function (more branching/if-statements = higher score).
2. **Turn that structure into something searchable.** Each function/class becomes a chunk of text, converted into a vector (a list of numbers representing its meaning) using Google's embedding model, and stored in a vector database called ChromaDB.
3. **Answer questions using only real code.** When a developer asks something like "How does retry logic work?", the system finds the most relevant chunks from step 2, hands them to an AI model (Gemini) along with strict instructions: answer only from this code, cite the file and function, and say "I don't know" rather than guess if the answer isn't there.
4. **Flag confusing code separately.** A second, independent feature called the confusion score combines three signals — how complex a function is, how often developers actually ask about it, and whether it has documentation — into one score that ranks which parts of a codebase are most likely to trip up a newcomer.

**One-sentence contrast that examiners like:** "A normal AI chatbot answers from what it was trained on. DevPulse answers from what's actually in front of it."

---

## 3. Tech stack — what we used, and why (be ready to justify each choice)

| Component | Tool | Why this one |
|---|---|---|
| Code parsing | Tree-sitter + tree-sitter-python | Industry-standard, language-aware parser; gives a real abstract syntax tree (AST), not just text matching |
| Embeddings | Google gemini-embedding-001 | Purpose-built for retrieval; has separate modes for "storing a document" vs. "asking a question," which improves match quality |
| Vector database | ChromaDB | Free, runs locally, simple to set up for a proof-of-concept |
| Answer generation | Google gemini-3.6-flash | Fast and cheap, which matters when you're running hundreds of test questions |
| Implementation help | Gemini (via Colab) | Used as a coding assistant to write and debug the pipeline |
| Manuscript drafting help | Claude | Used to help draft and structure the paper's text; every claim and citation was personally checked and verified, and this is formally disclosed in the paper itself |

**If asked "why not just use ChatGPT/a normal chatbot for this?"** — that's literally the baseline we tested against, and it's the whole point of the comparison (see Results).

---

## 4. Methodology — the evaluation, in one paragraph

We tested DevPulse against a "baseline" — the exact same AI model, same question, but with no access to the real code (it only gets told which repository the question is about, so the comparison is fair). We did this across **three repositories** chosen to differ in size and fame: **httpx** (small, famous, well-documented), **Flask** (medium, famous), and **TheAlgorithms/Python** (large, not famous as an individual repo). **12 questions per repository, asked to both systems = 36 questions, 72 total answers.** Each answer was scored for correctness, "groundedness" (does it only claim things it can actually verify), and categorized (correct / hallucination / refusal).

## 5. The numbers (memorize these exactly — likely to be asked directly)

| Repository | Baseline Correctness | Baseline Groundedness | DevPulse Correctness | DevPulse Groundedness |
|---|---|---|---|---|
| httpx | 4.00 / 5 | 3.00 / 5 | **5.00 / 5** | **5.00 / 5** |
| Flask | 4.00 / 5 | 3.00 / 5 | **5.00 / 5** | **5.00 / 5** |
| Algorithms | 2.00 / 5 | 2.00 / 5 | **5.00 / 5** | **5.00 / 5** |

- DevPulse: **perfect score on every repository, zero hallucinations across all 36 grounded answers.**
- Baseline: **hallucinated on all 12 questions** about the Algorithms repository, but did reasonably well on httpx/Flask.

Scale: every "/5" means a 1-to-5 rating, 5 is best.

---

## 6. The key finding — your strongest talking point: "The Familiarity Effect"

This is the single most important thing to say well in the viva, because it's the paper's actual contribution, not just "we built a chatbot."

> "The baseline AI did okay on httpx and Flask — but that's not because it's smart, it's because those are extremely famous libraries it likely memorized during training. The moment we tested it on a less famous codebase, it fell apart and started making things up. So the real finding is: **grounding helps the most exactly where you need it most** — on a codebase the AI doesn't already know, like a private company's internal code. Testing only on famous public libraries would have hidden this and made the baseline look better than it really is."

If pushed further: "This means DevPulse's real value isn't proven by testing on code the AI already half-knows — it's proven by testing on code it doesn't. Our Algorithms repo result is really the headline result, not httpx/Flask."

## 7. The confusion score — second contribution, don't forget this one

Formula: **ConfusionScore = (Complexity + Query Frequency + Documentation Penalty) / 3**

In plain words: a function scores as "confusing" if it's structurally complex, gets asked about a lot by developers, and/or has no documentation. It worked well on httpx — correctly identified httpx's own hand-written URL parser (very complex, zero documentation) as the single most confusing function in the whole codebase, even though almost nobody had asked about it yet. That's the point: a function doesn't need to have been asked about already to be flagged as likely-confusing.

**Honest limitation to volunteer if asked about this feature:** on the largest repository (Algorithms), we only had enough real questions to cover about 5% of all functions, so that specific repo's confusion ranking is less trustworthy — we say this directly in the paper rather than hide it.

---

## 8. If asked "what are the limitations / what would you do differently?"

Say these plainly, don't be defensive — a faculty panel respects honesty here:
- Only tested on 3 repositories, 36 questions total — small scale for a definitive claim
- Didn't run a real human user study (measuring actual time saved) — this round was accuracy/hallucination only, by design
- Scoring was done by an AI judge (a different AI than the one being tested, to avoid bias), checked against a smaller human-verified sample rather than full manual review of every answer
- Confusion score weights are untuned — equal weighting, not proven optimal
- Everything tested on Python only

## 9. If asked "what's next / future work?"

- Test on more repositories, including a genuinely private/unfamous one, to properly prove the familiarity effect
- Run an actual live user study with real developers
- Tune the confusion score with more real usage data over time
- Try smarter retrieval using the code's actual call-graph/import structure, not just text similarity

---

## 10. Publication status — a strong, honest thing to mention if asked "what's the impact/output of this project?"

> "We didn't just submit this as a college report — we took it through real academic peer review. It was submitted to the Journal of Systems and Software, then Information and Software Technology after a transfer, and is currently under review at the Journal of Computer Languages (Elsevier, Scopus-indexed) after passing initial editorial screening — meaning it's currently with real external reviewers, not just desk-rejected."

Only mention the two earlier rejections if asked directly — frame them honestly as normal parts of the academic process (one said "try a more specialized venue first," which is exactly what we did), not as a failure.

---

## 11. Quick glossary — rapid recall if a term comes up cold

- **RAG (Retrieval-Augmented Generation):** look up real information first, then let the AI answer using only that information
- **AST (Abstract Syntax Tree):** a structured, tree-shaped representation of code's actual structure, not just raw text
- **Embedding:** converting text into a list of numbers that represents its meaning, so similar meanings end up as similar numbers
- **Vector database:** a database built to quickly find the "closest meaning" matches among embeddings
- **Cyclomatic complexity:** a number measuring how many different logical paths a function can take (more if/for/while = higher)
- **Hallucination:** when an AI confidently states something false
- **Groundedness:** whether an answer is actually tied to real, checkable evidence, not just whether it happens to be right
- **Baseline:** the comparison system (plain AI, no retrieval) used to prove DevPulse's grounding actually helps

---

## 12. If you genuinely don't know an answer

Better to say: "That's a good question — we didn't test that directly in this round, but based on [X], I'd expect..." than to guess confidently. Faculty generally respond better to honest reasoning than to bluffing, and you already have the actual Limitations list (Section 8) ready to lean on for almost any "but what about..." question.
