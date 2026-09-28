"""Run the hand-written eval set through the RAG pipeline and score it with the RAG triad via Phoenix."""
import json
from pathlib import Path

from phoenix.evals import LLM, create_classifier
from phoenix.evals.metrics import FaithfulnessEvaluator, RetrievalRelevanceEvaluator

from generate import answer

CACHE_PATH = Path("data/eval_cache.json")
RETRIEVAL_METHOD = "vector"  # only retrieval method built so far; kept in the cache key for future methods

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


def _load_cache() -> dict:
    """Load cached (question, retrieval method) -> answer results, if any exist."""
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def _save_cache(cache: dict) -> None:
    """Persist the answer cache to disk."""
    CACHE_PATH.parent.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def get_cached_answer(question: str, cache: dict) -> dict:
    """Return the cached answer for (question, retrieval method) if present, else generate and cache it."""
    cache_key = f"{RETRIEVAL_METHOD}::{question}"
    if cache_key not in cache:
        cache[cache_key] = answer(question)
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


def run_eval() -> list[dict]:
    """Run every eval question through the RAG pipeline (cached) and score it with the RAG triad."""
    cache = _load_cache()
    llm = LLM(provider="openai", model="gpt-4.1-mini")
    context_relevance_eval = RetrievalRelevanceEvaluator(llm=llm)
    groundedness_eval = FaithfulnessEvaluator(llm=llm)
    answer_relevance_eval = build_answer_relevance_evaluator(llm)

    results = []
    for item in EVAL_SET:
        question, category = item["question"], item["category"]
        result = get_cached_answer(question, cache)
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


if __name__ == "__main__":
    eval_results = run_eval()

    total_tokens = sum(r["tokens"] for r in eval_results)
    total_latency = sum(r["latency"] for r in eval_results)
    print(f"{len(eval_results)} questions | total tokens: {total_tokens} | total latency: {total_latency:.1f}s")
    for metric in ("context_relevance", "groundedness", "answer_relevance"):
        avg = sum(r[metric] for r in eval_results) / len(eval_results)
        print(f"avg {metric}: {avg:.2f}")
