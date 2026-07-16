"""Evaluation framework — ground-truth scenarios with scoring metrics.

Each EvalCase defines a scenario with known correct answers.
Running eval measures: severity accuracy, root cause recall,
fix relevance, hallucination rate, and tool efficiency.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from .agent import analyze
from .k8s_client import set_scenario


class EvalCase(BaseModel):
    """A single evaluation case with ground truth."""

    id: str
    scenario: str
    description: str
    focus_pod: str | None = None
    expected_severity: str  # "Healthy", "Degraded", "Critical"
    expected_root_cause_keywords: list[str] = []  # keywords that should appear in root cause
    expected_fix_keywords: list[str] = []  # keywords that should appear in suggested fix
    expected_issue_pods: list[str] = []  # pod names that should appear in issues


class EvalResult(BaseModel):
    """Result of evaluating one case."""

    case_id: str
    passed: bool
    severity_correct: bool
    root_cause_recall: float  # 0.0 - 1.0
    fix_relevance: float  # 0.0 - 1.0
    issue_pod_coverage: float  # 0.0 - 1.0
    hallucinated_pods: list[str] = []
    iterations: int = 0
    latency_ms: int = 0
    model: str = ""
    notes: str = ""


class EvalReport(BaseModel):
    """Full evaluation report across all cases."""

    results: list[EvalResult]
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    avg_severity_accuracy: float = 0.0
    avg_root_cause_recall: float = 0.0
    avg_fix_relevance: float = 0.0
    avg_iterations: float = 0.0
    avg_latency_ms: float = 0.0
    model: str = ""


# ── Ground truth cases ─────────────────────────────────────────────

EVAL_CASES: list[EvalCase] = [
    EvalCase(
        id="crashloop-payment",
        scenario="solo-crashloop",
        description="Payment processor in CrashLoopBackOff with circuit breaker trip",
        expected_severity="Critical",
        expected_root_cause_keywords=["circuit breaker", "upstream", "timeout", "payment gateway"],
        expected_fix_keywords=["check upstream", "network", "payment gateway", "retry"],
        expected_issue_pods=["payment-processor"],
    ),
    EvalCase(
        id="error-disk-full",
        scenario="solo-error",
        description="ML training job failing due to disk full",
        expected_severity="Critical",
        expected_root_cause_keywords=["disk", "space", "storage", "device"],
        expected_fix_keywords=["disk", "storage", "cleanup", "volume", "expand"],
        expected_issue_pods=["ml-training-job"],
    ),
    EvalCase(
        id="imagepull-analytics",
        scenario="solo-imagepull",
        description="Analytics ETL with ImagePullBackOff — manifest not found",
        expected_severity="Critical",
        expected_root_cause_keywords=["image", "pull", "manifest", "tag", "registry"],
        expected_fix_keywords=["image", "tag", "registry", "repository"],
        expected_issue_pods=["analytics-etl"],
    ),
    EvalCase(
        id="pending-cache",
        scenario="solo-pending",
        description="Redis cache stuck in Pending due to insufficient CPU",
        expected_severity="Degraded",
        expected_root_cause_keywords=["cpu", "scheduling", "resource", "insufficient", "node"],
        expected_fix_keywords=["resource", "cpu", "node", "scale", "limit"],
        expected_issue_pods=["cache-redis"],
    ),
    EvalCase(
        id="oom-recommend",
        scenario="solo-oom",
        description="Recommendation engine OOMKilled — model too large for container",
        expected_severity="Critical",
        expected_root_cause_keywords=["memory", "oom", "out of memory", "allocation", "bad_alloc"],
        expected_fix_keywords=["memory", "limit", "resource", "resize", "larger"],
        expected_issue_pods=["recommend-engine"],
    ),
    EvalCase(
        id="healthy-all",
        scenario="healthy",
        description="All pods healthy — agent should report no issues",
        expected_severity="Healthy",
        expected_root_cause_keywords=[],
        expected_fix_keywords=[],
        expected_issue_pods=[],
    ),
]


# ── Scoring helpers ────────────────────────────────────────────────


def _keyword_recall(text: str, keywords: list[str]) -> float:
    """Measure what fraction of expected keywords appear in the text."""
    if not keywords:
        return 1.0  # no keywords expected = trivially satisfied
    text_lower = text.lower()
    found = sum(1 for kw in keywords if kw.lower() in text_lower)
    return found / len(keywords)


def _detect_hallucinated_pods(answer: str, valid_pods: list[str]) -> list[str]:
    """Find pod names mentioned in the answer that don't exist in the cluster."""
    # Look for patterns like ### pod-name — namespace
    mentioned = re.findall(r"###\s+(\S+)", answer)
    invalid = [m for m in mentioned if m not in valid_pods and m != "[pod"]
    return list(set(invalid))


def _extract_health_score(answer: str) -> str:
    match = re.search(r"Overall Health Score:\s*(.+)", answer, re.IGNORECASE)
    return match.group(1).strip() if match else "Unknown"


# ── Evaluation runner ──────────────────────────────────────────────


def run_eval(
    model: str | None = None,
    cases: list[EvalCase] | None = None,
) -> EvalReport:
    """Run all evaluation cases and produce a report.

    Uses mock data (no real cluster needed).
    """
    eval_cases = cases or EVAL_CASES
    results: list[EvalResult] = []

    for case in eval_cases:
        set_scenario(case.scenario)
        answer, trace = analyze(
            focus_pod=case.focus_pod,
            model=model,
            scenario=case.scenario,
        )

        # Score severity
        detected_score = _extract_health_score(answer)
        severity_correct = detected_score.lower() == case.expected_severity.lower()

        # Score root cause
        root_cause_recall = _keyword_recall(answer, case.expected_root_cause_keywords)

        # Score fix relevance
        fix_relevance = _keyword_recall(answer, case.expected_fix_keywords)

        # Score issue pod coverage
        if case.expected_issue_pods:
            found_pods = sum(1 for p in case.expected_issue_pods if p.lower() in answer.lower())
            issue_pod_coverage = found_pods / len(case.expected_issue_pods)
        else:
            # For healthy scenario, coverage is 1.0 if no issues are incorrectly reported
            bad_pattern = r"###\s+\S+.*(CrashLoop|Error|OOM)"
            issue_pod_coverage = 1.0 if not re.search(bad_pattern, answer) else 0.0

        # Hallucination check
        # For mock data, valid pods depend on the scenario
        from .k8s_client import get_pods

        pods = get_pods()
        valid_names = [p.name for p in pods]
        hallucinated = _detect_hallucinated_pods(answer, valid_names)

        passed = severity_correct and root_cause_recall >= 0.5 and len(hallucinated) == 0

        results.append(
            EvalResult(
                case_id=case.id,
                passed=passed,
                severity_correct=severity_correct,
                root_cause_recall=root_cause_recall,
                fix_relevance=fix_relevance,
                issue_pod_coverage=issue_pod_coverage,
                hallucinated_pods=hallucinated,
                iterations=trace.iterations,
                latency_ms=trace.total_latency_ms,
                model=trace.model or model or "",
            )
        )

    # Aggregate
    n = len(results)
    report = EvalReport(
        results=results,
        total_cases=n,
        passed=sum(1 for r in results if r.passed),
        failed=sum(1 for r in results if not r.passed),
        avg_severity_accuracy=sum(r.severity_correct for r in results) / n if n else 0,
        avg_root_cause_recall=sum(r.root_cause_recall for r in results) / n if n else 0,
        avg_fix_relevance=sum(r.fix_relevance for r in results) / n if n else 0,
        avg_iterations=sum(r.iterations for r in results) / n if n else 0,
        avg_latency_ms=sum(r.latency_ms for r in results) / n if n else 0,
        model=model or "",
    )
    return report


def run_eval_for_model(model_id: str) -> EvalReport:
    """Convenience: run full eval suite for a specific model."""
    return run_eval(model=model_id)
