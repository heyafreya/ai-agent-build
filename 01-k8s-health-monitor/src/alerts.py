"""Alert threshold rules for the K8s health agent.

Each rule is a simple check against a PodInfo.
Works independent of the LLM, providing a robust health
assessment of each pod.

Severities:
- critical: immediate action needed
- warning: investigate
- healthy: all good
"""

from .k8s_client import PodInfo

# Severity order for sorting
SEVERITY_ORDER = {"healthy": 0, "warning": 1, "critical": 2}

# Statuses that map directly to severities
CRITICAL_STATUSES = {
    "CrashLoopBackOff",
    "Error",
    "ImagePullBackOff",
    "OOMKilled",
    "Unknown",
}
WARNING_STATUSES = {"Pending", "Evicted", "Terminating", "Init:CrashLoop"}


def score_pod(pod: PodInfo) -> str:
    """Score a PodInfo returning severity as a string."""
    if pod.status in CRITICAL_STATUSES:
        return "critical"
    if pod.status in WARNING_STATUSES:
        return "warning"
    if "Running" in pod.status or "Completed" in pod.status:
        if pod.restarts >= 5:
            return "critical"
        if pod.restarts >= 3:
            return "warning"
        ready_ratio = pod.ready.split("/")
        if len(ready_ratio) == 2:
            try:
                num = int(ready_ratio[0])
                den = int(ready_ratio[1])
                if num == 0 and den > 0:
                    return "critical"
                if num < den:
                    return "warning"
            except ValueError:
                return "warning"
        return "healthy"
    return "warning"


def sorted_pods(pods: list[PodInfo]) -> list[PodInfo]:
    """Return pods sorted by severity descending."""
    return sorted(
        pods,
        key=lambda p: SEVERITY_ORDER.get(score_pod(p), 0),
        reverse=True,
    )


def severity_counts(pods: list[PodInfo]) -> dict[str, int]:
    """Return object with count of each severity."""
    counts = {"critical": 0, "warning": 0, "healthy": 0}
    for p in pods:
        s = score_pod(p)
        if s in counts:
            counts[s] += 1
    return counts


def severity_stats(pods: list[PodInfo]) -> str:
    """Return a one-line string summary of pod health.
    Example: "2 critical, 1 warning, 5 healthy"
    """
    counts = severity_counts(pods)
    parts = []
    for sev in ("critical", "warning", "healthy"):
        if counts[sev] > 0:
            label = f"{counts[sev]} {sev}"
            if counts[sev] > 1:
                label += "s"
            parts.append(label)
    return ", ".join(parts) if parts else "0 pods"
