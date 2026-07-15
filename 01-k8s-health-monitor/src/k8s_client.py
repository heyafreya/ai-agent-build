"""Kubernetes client — collects pod data via kubectl (or mock data for dev).

Design notes:
- Uses subprocess + kubectl for simplicity and zero dependencies.
- Falls back to realistic mock data when no cluster is available.
- The Python kubernetes SDK is an alternative, but requires the same
  kubeconfig and adds complexity without benefit for read-only queries.
"""

import json
import subprocess
import time
from typing import Optional

from pydantic import BaseModel


class PodInfo(BaseModel):
    name: str
    namespace: str
    status: str
    restarts: int
    age: str
    ready: str  # e.g. "1/1"
    node: str
    conditions: list[str] = []


def _has_kubectl() -> bool:
    try:
        subprocess.run(
            ["kubectl", "version", "--client"],
            capture_output=True,
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _cluster_reachable() -> bool:
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info", "--request-timeout=3"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# ── Mock data for development without a cluster ──────────────────────

_MOCK_PODS = [
    {
        "name": "nginx-deploy-7c8b9d4f8f-abc12",
        "namespace": "default",
        "status": "Running",
        "restarts": 0,
        "age": "12d",
        "ready": "1/1",
        "node": "kind-control-plane",
    },
    {
        "name": "api-server-6f4d7c9b8f-x9y3z",
        "namespace": "default",
        "status": "Running",
        "restarts": 1,
        "age": "45d",
        "ready": "1/1",
        "node": "kind-control-plane",
    },
    {
        "name": "redis-cache-d9f8a7b6c5-p4q2r",
        "namespace": "cache",
        "status": "Running",
        "restarts": 3,
        "age": "3d",
        "ready": "1/1",
        "node": "kind-worker",
    },
    {
        "name": "postgres-statefulset-0",
        "namespace": "database",
        "status": "Running",
        "restarts": 0,
        "age": "60d",
        "ready": "1/1",
        "node": "kind-worker2",
    },
    {
        "name": "payment-worker-7d4a8f2c3e-f1g2h",
        "namespace": "payments",
        "status": "CrashLoopBackOff",
        "restarts": 15,
        "age": "2d",
        "ready": "0/1",
        "node": "kind-worker",
    },
    {
        "name": "frontend-deploy-5f6g7h8j9k-l4m5n",
        "namespace": "frontend",
        "status": "Running",
        "restarts": 0,
        "age": "7d",
        "ready": "1/1",
        "node": "kind-control-plane",
    },
    {
        "name": "analytics-job-9a8b7c6d5e-q1w2e",
        "namespace": "analytics",
        "status": "Pending",
        "restarts": 0,
        "age": "30m",
        "ready": "0/1",
        "node": "kind-worker",
    },
    {
        "name": "sidecar-injector-8f7g6h5j4k-r3t4y",
        "namespace": "kube-system",
        "status": "Running",
        "restarts": 0,
        "age": "90d",
        "ready": "2/2",
        "node": "kind-control-plane",
    },
    {
        "name": "monitoring-agent-d4f5g6h7j8-s9u0i",
        "namespace": "monitoring",
        "status": "ImagePullBackOff",
        "restarts": 0,
        "age": "1h",
        "ready": "0/1",
        "node": "kind-worker2",
    },
    {
        "name": "cron-job-scheduler-6h5g4f3d2s-a1b2c",
        "namespace": "default",
        "status": "Running",
        "restarts": 2,
        "age": "30d",
        "ready": "1/1",
        "node": "kind-worker",
    },
]


def _get_live_pods(namespace: Optional[str] = None) -> list[dict]:
    """Fetch real pods via kubectl."""
    cmd = ["kubectl", "get", "pods"]
    if namespace:
        cmd.extend(["-n", namespace])
    else:
        cmd.append("-A")
    cmd.extend(["-o", "json", "--request-timeout=10"])

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    pods = []
    for item in data.get("items", []):
        status = item["status"]
        container_statuses = status.get("containerStatuses", [])
        restarts = sum(cs.get("restartCount", 0) for cs in container_statuses)
        ready_containers = sum(
            1 for cs in container_statuses if cs.get("ready")
        )
        total_containers = len(container_statuses)

        # Determine the effective pod phase/status
        phase = status.get("phase", "Unknown")
        if phase == "Running":
            # Check for CrashLoopBackOff in container state
            for cs in container_statuses:
                waiting = cs.get("state", {}).get("waiting", {})
                if waiting.get("reason") in ("CrashLoopBackOff", "Error"):
                    phase = "CrashLoopBackOff"
                    break

        pods.append(
            {
                "name": item["metadata"]["name"],
                "namespace": item["metadata"]["namespace"],
                "status": phase,
                "restarts": restarts,
                "age": _compute_age(item["metadata"].get("creationTimestamp", "")),
                "ready": f"{ready_containers}/{total_containers}",
                "node": item["spec"].get("nodeName", "unknown"),
            }
        )

    return pods


def _compute_age(creation_timestamp: str) -> str:
    """Convert ISO timestamp to human-readable age (approximate)."""
    from datetime import datetime, timezone
    try:
        created = datetime.fromisoformat(creation_timestamp.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - created
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0:
            return f"{days}d"
        return f"{hours}h"
    except Exception:
        return "unknown"


def get_pods(namespace: Optional[str] = None) -> list[PodInfo]:
    """Collect pod information from the cluster or mock data.

    Auto-detects whether a real cluster is available.
    """
    if _has_kubectl() and _cluster_reachable():
        raw_pods = _get_live_pods(namespace)
    else:
        raw_pods = _MOCK_PODS
        if namespace:
            raw_pods = [p for p in raw_pods if p["namespace"] == namespace]

    return [PodInfo(**p) for p in raw_pods]


def describe_pod(name: str, namespace: str = "default") -> str:
    """Get detailed pod description (events, conditions, container states)."""
    if _has_kubectl() and _cluster_reachable():
        result = subprocess.run(
            ["kubectl", "describe", "pod", name, "-n", namespace],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    else:
        return f"(mock) kubectl describe pod {name} -n {namespace}"
