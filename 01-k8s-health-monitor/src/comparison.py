"""Model comparison — runs the same scenario across multiple LLM providers.

Tracks latency, token usage, and analysis quality for side-by-side comparison.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from .agent import AgentTrace, analyze


class ComparisonResult(BaseModel):
    """Result of running the agent with one model."""

    model: str
    answer: str
    trace: AgentTrace
    latency_ms: int
    tokens_in: int
    tokens_out: int
    health_score: str = ""
    issue_count: int = 0
    error: str | None = None


# Models to compare — ordered by cost (cheapest first)
COMPARISON_MODELS = [
    ("gemini/gemini-2.0-flash-exp", "Gemini 2.0 Flash"),
    ("openai/gpt-4o-mini", "GPT-4o Mini"),
    ("anthropic/claude-3-5-haiku-20241022", "Claude 3.5 Haiku"),
    ("ollama/llama3.2:3b", "Llama 3.2 3B (local)"),
    ("ollama/mistral:7b", "Mistral 7B (local)"),
]

_MODEL_LABELS = {m[0]: m[1] for m in COMPARISON_MODELS}


def _run_single_model(
    model_id: str,
    namespace: str | None,
    focus_pod: str | None,
    scenario: str,
) -> ComparisonResult:
    """Run the agent with a single model and capture results."""
    start = time.perf_counter()
    try:
        answer, trace = analyze(
            namespace=namespace,
            focus_pod=focus_pod,
            model=model_id,
            scenario=scenario,
        )
        latency = int((time.perf_counter() - start) * 1000)

        # Extract health score from the answer
        health_score = "Unknown"
        import re

        score_match = re.search(r"##\s*Overall Health Score:\s*(.+)", answer, re.IGNORECASE)
        if score_match:
            health_score = score_match.group(1).strip()

        # Count issues (### headings in the Issues Found section)
        issue_count = len(re.findall(r"###\s+.+", answer))

        return ComparisonResult(
            model=model_id,
            answer=answer,
            trace=trace,
            latency_ms=latency,
            tokens_in=trace.total_tokens_in,
            tokens_out=trace.total_tokens_out,
            health_score=health_score,
            issue_count=issue_count,
        )
    except Exception as e:
        latency = int((time.perf_counter() - start) * 1000)
        return ComparisonResult(
            model=model_id,
            answer="",
            trace=AgentTrace(model=model_id),
            latency_ms=latency,
            tokens_in=0,
            tokens_out=0,
            error=str(e),
        )


def compare_models(
    namespace: str | None = None,
    focus_pod: str | None = None,
    scenario: str = "composite",
    models: list[str] | None = None,
) -> list[ComparisonResult]:
    """Run the same scenario across multiple models in parallel.

    If models is None, runs all comparison models.
    Returns a list of ComparisonResult sorted by latency.
    """
    target_models = models or [m[0] for m in COMPARISON_MODELS]
    results = []

    with ThreadPoolExecutor(max_workers=min(len(target_models), 4)) as pool:
        futures = {pool.submit(_run_single_model, m, namespace, focus_pod, scenario): m for m in target_models}
        for future in futures:
            results.append(future.result())

    results.sort(key=lambda r: r.latency_ms)
    return results


def get_model_label(model_id: str) -> str:
    """Return a human-readable label for a model ID."""
    return _MODEL_LABELS.get(model_id, model_id)
