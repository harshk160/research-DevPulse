"""
Task 11 — Manual review rubric / scoring tool.

Blind, console-based scoring loop: for each (repo, question) pair it shows
the baseline and RAG answers as unlabeled "A"/"B", collects a 1-5
correctness score, a 1-5 groundedness score, and a category
(correct_answer / correct_refusal / incorrect_refusal / hallucination) for
each, then de-anonymizes and appends to evaluation_scores.csv. Safe to
stop (type 'q') and resume later — already-scored pairs are skipped.
"""

import os
import csv
import json
import random
from IPython.display import clear_output


def get_valid_input(prompt: str, valid_options: list) -> str:
    while True:
        val = input(prompt).strip().lower()
        if val in valid_options:
            return val
        print(f"Invalid input. Please enter one of: {', '.join(valid_options)}")


def manual_evaluation_loop(input_json_path: str, output_csv_path: str = "evaluation_scores.csv"):
    with open(input_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Group data by (repo, question_id)
    grouped_data = {}
    for item in data:
        key = (item['repo'], item['question_id'])
        if key not in grouped_data:
            grouped_data[key] = {
                'repo': item['repo'],
                'question_id': item['question_id'],
                'question_text': item['question_text']
            }
        grouped_data[key][item['system']] = item

    completed_evals = set()
    if os.path.exists(output_csv_path):
        with open(output_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                completed_evals.add((row['repo'], row['question_id'], row['system']))
    else:
        with open(output_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["trial_id", "repo", "question_id", "system", "correctness", "groundedness", "category", "note"])

    categories = {
        "1": "correct_answer",
        "2": "correct_refusal",
        "3": "incorrect_refusal",
        "4": "hallucination"
    }

    for key, group in grouped_data.items():
        repo, q_id = key

        if 'baseline' not in group or 'rag' not in group:
            continue

        if (repo, q_id, 'baseline') in completed_evals and (repo, q_id, 'rag') in completed_evals:
            continue

        clear_output(wait=True)
        print("=" * 80)
        print(f"REPO: {repo} | QUESTION ID: {q_id}")
        print("=" * 80)
        print(f"QUESTION:\n{group['question_text']}\n")
        print("=" * 80)

        # Randomize A/B order for blind scoring
        systems = ['baseline', 'rag']
        random.shuffle(systems)
        sys_a, sys_b = systems[0], systems[1]

        print(f"--- ANSWER A ---\n{group[sys_a]['answer_text']}\n")
        print(f"--- ANSWER B ---\n{group[sys_b]['answer_text']}\n")
        print("=" * 80)
        print("Type 'q' at any prompt to save and quit.")

        scores = {}
        for label, true_sys in [('A', sys_a), ('B', sys_b)]:
            if (repo, q_id, true_sys) in completed_evals:
                print(f"\nAnswer {label} already evaluated.")
                continue

            print(f"\n--- SCORING ANSWER {label} ---")
            corr = get_valid_input("Correctness (1-5): ", ["1", "2", "3", "4", "5", "q"])
            if corr == 'q':
                return

            ground = get_valid_input("Groundedness (1-5): ", ["1", "2", "3", "4", "5", "q"])
            if ground == 'q':
                return

            print("Categories:\n[1] correct_answer\n[2] correct_refusal\n[3] incorrect_refusal\n[4] hallucination")
            cat_choice = get_valid_input("Category (1-4): ", ["1", "2", "3", "4", "q"])
            if cat_choice == 'q':
                return

            note = input("Optional note (Enter to skip): ").strip()

            # Map the blind score back to the true trial identity
            scores[true_sys] = [
                group[true_sys]['trial_id'], repo, q_id, true_sys,
                corr, ground, categories[cat_choice], note
            ]

        if scores:
            with open(output_csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for sys_key, row_data in scores.items():
                    writer.writerow(row_data)
                    completed_evals.add((repo, q_id, sys_key))

    clear_output(wait=True)
    print("All evaluations complete!")


def generate_evaluation_summary(csv_path: str = "evaluation_scores.csv"):
    if not os.path.exists(csv_path):
        print(f"No evaluation data found at {csv_path}.")
        return

    stats = {
        "baseline": {"correctness": [], "groundedness": [], "categories": {}},
        "rag": {"correctness": [], "groundedness": [], "categories": {}}
    }

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sys = row["system"]
            if sys not in stats:
                continue

            stats[sys]["correctness"].append(int(row["correctness"]))
            stats[sys]["groundedness"].append(int(row["groundedness"]))

            cat = row["category"]
            stats[sys]["categories"][cat] = stats[sys]["categories"].get(cat, 0) + 1

    print("\n" + "=" * 50)
    print(" DEVPULSE EVALUATION SUMMARY")
    print("=" * 50)

    cat_keys = ["correct_answer", "correct_refusal", "incorrect_refusal", "hallucination"]

    for sys in ["baseline", "rag"]:
        c_scores = stats[sys]["correctness"]
        g_scores = stats[sys]["groundedness"]
        total = len(c_scores)

        if total == 0:
            print(f"\nSYSTEM: {sys.upper()} (No evaluations found)")
            continue

        avg_c = sum(c_scores) / total
        avg_g = sum(g_scores) / total

        print(f"\n[SYSTEM: {sys.upper()}] (Total Evaluated: {total})")
        print("-" * 50)
        print(f"Average Correctness:  {avg_c:.2f} / 5.0")
        print(f"Average Groundedness: {avg_g:.2f} / 5.0")
        print("Category Breakdown:")

        for cat in cat_keys:
            count = stats[sys]["categories"].get(cat, 0)
            pct = (count / total) * 100 if total > 0 else 0
            print(f"  - {cat:<20}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    manual_evaluation_loop("devpulse_evaluation_batch.json", "evaluation_scores.csv")
    generate_evaluation_summary("evaluation_scores.csv")
