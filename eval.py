"""Run the hand-written eval set through the RAG pipeline and score it with the RAG triad via Phoenix."""
import argparse
import json
import sys
from pathlib import Path

from phoenix.evals import LLM, create_classifier
from phoenix.evals.metrics import FaithfulnessEvaluator, RetrievalRelevanceEvaluator

from generate import answer

CACHE_PATH = Path("data/eval_cache.json")

# Regression gate (core set, vector method): eval.py exits 1 if any RAG-triad average falls below its floor.
# Floors sit below measured scores (0.83 / 0.94 / 1.00) to absorb judge noise: groundedness alone moved
# 1.00 -> 0.94 on identical cached answers, so a 0.95 floor would fail on noise.
GATE_THRESHOLDS = {"context_relevance": 0.75, "groundedness": 0.90, "answer_relevance": 0.90}

# Hand-written eval set on Alphabet (GOOGL) and Micron (MU) only, per project scope.
EVAL_SET = [
    {"question": "What was Alphabet's total revenue?", "category": "factual"},
    {"question": "What was Micron's total revenue?", "category": "factual"},
    {"question": "What was Alphabet's net income?", "category": "factual"},
    {"question": "What was Micron's net income?", "category": "factual"},
    {"question": "How much did Alphabet spend on research and development?", "category": "factual"},
    {"question": "What was Micron's total operating expenses?", "category": "factual"},
    {"question": "Which company had higher revenue, Alphabet or Micron?", "category": "cross_company"},
    {"question": "Which company had higher net income, Alphabet or Micron?", "category": "cross_company"},
    {"question": "Which company spent more on research and development, Alphabet or Micron?", "category": "cross_company"},
    {"question": "How did Alphabet's revenue change year over year?", "category": "cross_year"},
    {"question": "How did Micron's revenue change year over year?", "category": "cross_year"},
    {"question": "Did Micron's net income improve or decline compared to the prior year?", "category": "cross_year"},
    {"question": "How did Alphabet's net income change between the two most recent fiscal years?", "category": "cross_year"},
    {"question": "What is Alphabet's current stock price?", "category": "should_abstain"},
    {"question": "Who is Micron's Chief Executive Officer's favorite hobby?", "category": "should_abstain"},
    {"question": "What will Alphabet's revenue be next fiscal year?", "category": "should_abstain"},
    {"question": "What was Apple's revenue last year?", "category": "should_abstain"},
    {"question": "What is Micron's stance on cryptocurrency investment?", "category": "should_abstain"},
]

# Separate keyword_exact set (exact figures / specific terms), reported apart from the original 18 above.
# Written from chunks actually stored in Chroma; see NOTES.md Step 7.
KEYWORD_EVAL_SET = [
    {"question": "By what percentage did Micron's CMBU revenue increase in fiscal 2025 compared to 2024?", "category": "keyword_exact"},
    {"question": "What is the interest rate on Micron's 2029 B Notes?", "category": "keyword_exact"},
    {"question": "On which DRAM node was the majority of Micron's 2025 DRAM bit production?", "category": "keyword_exact"},
    {"question": "By how much did Alphabet's Google Cloud revenues increase from 2024 to 2025?", "category": "keyword_exact"},
    {"question": "How many shares did Alphabet repurchase in 2025, and for how much?", "category": "keyword_exact"},
    {"question": "What is the name of Alphabet's seventh-generation TPU?", "category": "keyword_exact"},
]


def _load_cache() -> dict:
    """Load cached (question, retrieval method) -> answer results, if any exist."""
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def _save_cache(cache: dict) -> None:
    """Persist the answer cache to disk."""
    CACHE_PATH.parent.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def get_cached_answer(question: str, cache: dict, method: str = "vector") -> dict:
    """Return the cached answer for (question, retrieval method) if present, else generate and cache it."""
    cache_key = f"{method}::{question}"
    if cache_key not in cache:
        cache[cache_key] = answer(question, method=method)
        _save_cache(cache)
    return cache[cache_key]


def build_answer_relevance_evaluator(llm: LLM):
    """Build a custom answer-relevance classifier, since Phoenix has no built-in one under that name."""
    return create_classifier(
        name="answer_relevance",
        llm=llm,
        prompt_template=(
            "Question: {input}\nAnswer: {output}\n\n"
            "Does the answer directly address the question asked (regardless of whether "
            "it is correct)? Respond relevant or irrelevant."
        ),
        choices={"relevant": 1.0, "irrelevant": 0.0},
    )


def run_eval(method: str = "vector", eval_set: list[dict] = EVAL_SET, use_cache: bool = True) -> list[dict]:
    """Run every eval question through the RAG pipeline and score it with the RAG triad.

    use_cache=False regenerates every answer and never reads or writes data/eval_cache.json, so a code
    change that hurts retrieval actually shows up in the scores (CI's gate runs this way).
    """
    cache = _load_cache() if use_cache else {}
    llm = LLM(provider="openai", model="gpt-4.1-mini")
    context_relevance_eval = RetrievalRelevanceEvaluator(llm=llm)
    groundedness_eval = FaithfulnessEvaluator(llm=llm)
    answer_relevance_eval = build_answer_relevance_evaluator(llm)

    results = []
    for item in eval_set:
        question, category = item["question"], item["category"]
        result = get_cached_answer(question, cache, method) if use_cache else answer(question, method=method)
        eval_input = {"input": question, "output": result["answer"], "context": result["context"]}

        context_score = context_relevance_eval.evaluate(eval_input)[0]
        groundedness_score = groundedness_eval.evaluate(eval_input)[0]
        relevance_score = answer_relevance_eval.evaluate(eval_input)[0]
        usage = result["usage"]

        print(
            f"[{category}] {question}\n"
            f"  answer: {result['answer']}\n"
            f"  context_relevance={context_score.label}  groundedness={groundedness_score.label}  "
            f"answer_relevance={relevance_score.label}\n"
            f"  tokens={usage['total_tokens']}  latency={result['latency']:.2f}s\n"
        )
        results.append(
            {
                "question": question,
                "category": category,
                "answer": result["answer"],
                "context_relevance": context_score.score,
                "groundedness": groundedness_score.score,
                "answer_relevance": relevance_score.score,
                "tokens": usage["total_tokens"],
                "latency": result["latency"],
            }
        )

    return results


def gate_failures(results: list[dict]) -> list[str]:
    """Return one message per RAG-triad average below its GATE_THRESHOLDS floor; an empty list means the gate passes."""
    failures = []
    for metric, floor in GATE_THRESHOLDS.items():
        avg = sum(r[metric] for r in results) / len(results)
        if avg < floor:
            failures.append(f"{metric} {avg:.2f} < {floor:.2f}")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the RAG triad eval for one retrieval method and eval set.")
    parser.add_argument("--method", choices=("vector", "hybrid"), default="vector")
    parser.add_argument("--set", dest="eval_set", choices=("core", "keyword_exact"), default="core")
    parser.add_argument("--no-cache", action="store_true", help="regenerate answers; never read/write the answer cache")
    args = parser.parse_args()
    eval_results = run_eval(
        args.method, EVAL_SET if args.eval_set == "core" else KEYWORD_EVAL_SET, use_cache=not args.no_cache
    )

    total_tokens = sum(r["tokens"] for r in eval_results)
    total_latency = sum(r["latency"] for r in eval_results)
    print(f"[{args.method} / {args.eval_set}] {len(eval_results)} questions | total tokens: {total_tokens} | total latency: {total_latency:.1f}s")
    for metric in ("context_relevance", "groundedness", "answer_relevance"):
        avg = sum(r[metric] for r in eval_results) / len(eval_results)
        print(f"avg {metric}: {avg:.2f}")

    # Gate only the configuration the floors were calibrated on: core set, vector method.
    if args.method == "vector" and args.eval_set == "core":
        failures = gate_failures(eval_results)
        if failures:
            print("GATE FAILED: " + "; ".join(failures))
            sys.exit(1)
        print("GATE PASSED")
