"""Kubernetes client — collects pod data via kubectl (or mock data for dev).

Design notes:
- Uses subprocess + kubectl for simplicity and zero dependencies.
- Falls back to realistic mock data when no cluster is available.
- The Python kubernetes SDK is an alternative, but requires the same
  kubeconfig and adds complexity without benefit for read-only queries.
"""

import json
import random
import subprocess
from datetime import UTC

from pydantic import BaseModel


class PodInfo(BaseModel):
    name: str
    namespace: str
    status: str
    restarts: int
    age: str
    ready: str
    node: str
    conditions: list[str] = []


# ── Scenario selector ──────────────────────────────────────────────

_current_scenario: str = "mixed"


def set_scenario(name: str):
    global _current_scenario
    _current_scenario = name


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


# ── Healthy base pods (shared across scenarios) ────────────────────

_BASE_HEALTHY = [
    {
        "name": "web-frontend-6f8d9c4b5a-x1y2z",
        "namespace": "frontend",
        "status": "Running",
        "restarts": 0,
        "age": "14d",
        "ready": "3/3",
        "node": "kind-control-plane",
    },
    {
        "name": "api-gateway-7a9b8c6d5e-p3q4r",
        "namespace": "api",
        "status": "Running",
        "restarts": 1,
        "age": "60d",
        "ready": "2/2",
        "node": "kind-worker",
    },
    {
        "name": "user-service-db-0",
        "namespace": "database",
        "status": "Running",
        "restarts": 0,
        "age": "90d",
        "ready": "1/1",
        "node": "kind-worker2",
    },
    {
        "name": "auth-service-5f7g8h9j0k-l2m3n",
        "namespace": "security",
        "status": "Running",
        "restarts": 0,
        "age": "30d",
        "ready": "1/1",
        "node": "kind-control-plane",
    },
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
        "name": "cron-job-scheduler-6h5g4f3d2s-a1b2c",
        "namespace": "default",
        "status": "Running",
        "restarts": 2,
        "age": "30d",
        "ready": "1/1",
        "node": "kind-worker",
    },
]

# ── Unhealthy pod variations ───────────────────────────────────────

_BAD_CRASHLOOP = {
    "name": "payment-processor-b7c8d9e0f1-g5h6j",
    "namespace": "payments",
    "status": "CrashLoopBackOff",
    "restarts": 3,
    "age": "45m",
    "ready": "0/1",
    "node": "kind-worker",
}

_BAD_ERROR = {
    "name": "ml-training-job-4f5g6h7j8k-q2w3e",
    "namespace": "ml",
    "status": "Error",
    "restarts": 7,
    "age": "2h",
    "ready": "0/1",
    "node": "kind-worker",
}

_BAD_IMAGEPULL = {
    "name": "analytics-etl-9a8b7c6d5e-r4t5y",
    "namespace": "analytics",
    "status": "ImagePullBackOff",
    "restarts": 0,
    "age": "10m",
    "ready": "0/1",
    "node": "kind-worker2",
}

_BAD_PENDING = {
    "name": "cache-redis-2f4g6h8j0k-m3n4b",
    "namespace": "cache",
    "status": "Pending",
    "restarts": 0,
    "age": "5m",
    "ready": "0/1",
    "node": "kind-worker",
}

_BAD_OOM = {
    "name": "recommend-engine-d3f5g7h9j1-v2c4x",
    "namespace": "ml",
    "status": "OOMKilled",
    "restarts": 12,
    "age": "1h",
    "ready": "0/1",
    "node": "kind-worker",
}

# ── Scenarios ──────────────────────────────────────────────────────

_SCENARIO_HEALTHY = _BASE_HEALTHY.copy()

_SCENARIO_CRASHING = _BASE_HEALTHY.copy()
_SCENARIO_CRASHING.append(_BAD_CRASHLOOP)

# ── Original 10-pod mixed-health scenario ──────────────────────────

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

_SCENARIO_SOLO = {
    "crashloop": _BASE_HEALTHY.copy() + [_BAD_CRASHLOOP],
    "error": _BASE_HEALTHY.copy() + [_BAD_ERROR],
    "imagepull": _BASE_HEALTHY.copy() + [_BAD_IMAGEPULL],
    "pending": _BASE_HEALTHY.copy() + [_BAD_PENDING],
    "oom": _BASE_HEALTHY.copy() + [_BAD_OOM],
}

_SCENARIOS = {
    "healthy": _SCENARIO_HEALTHY,
    "crashing": _SCENARIO_CRASHING,
    "solo-crashloop": _SCENARIO_SOLO["crashloop"],
    "solo-error": _SCENARIO_SOLO["error"],
    "solo-imagepull": _SCENARIO_SOLO["imagepull"],
    "solo-pending": _SCENARIO_SOLO["pending"],
    "solo-oom": _SCENARIO_SOLO["oom"],
    "mixed": _MOCK_PODS,  # kept as-is for backward compat; use "composite" for dynamic
    "composite": "dynamic",  # handled in get_pods
}


def _get_live_pods(namespace: str | None = None) -> list[dict]:
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
        ready_containers = sum(1 for cs in container_statuses if cs.get("ready"))
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
    from datetime import datetime

    try:
        created = datetime.fromisoformat(creation_timestamp.replace("Z", "+00:00"))
        delta = datetime.now(UTC) - created
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0:
            return f"{days}d"
        return f"{hours}h"
    except Exception:
        return "unknown"


def _build_composite_scenario() -> list[dict]:
    """Build a dynamic mixed scenario by combining healthy base pods
    with a random selection of 2-3 bad pods."""
    bad_pool = [_BAD_CRASHLOOP, _BAD_ERROR, _BAD_IMAGEPULL, _BAD_PENDING, _BAD_OOM]
    count = random.randint(2, 3)
    selected = random.sample(bad_pool, count)
    return _BASE_HEALTHY.copy() + selected


def get_pods(namespace: str | None = None) -> list[PodInfo]:
    """Collect pod information from the cluster or mock data.

    Auto-detects whether a real cluster is available.
    """
    if _has_kubectl() and _cluster_reachable():
        raw_pods = _get_live_pods(namespace)
    else:
        found = _SCENARIOS.get(_current_scenario, _MOCK_PODS)
        raw_pods = _build_composite_scenario() if found == "dynamic" else found
        if namespace:
            raw_pods = [p for p in raw_pods if p["namespace"] == namespace]

    return [PodInfo(**p) for p in raw_pods]


_MOCK_DESCRIBE = {
    "payment-processor": (
        "Name:             payment-processor-b7c8d9e0f1-g5h6j\n"
        "Namespace:        payments\n"
        "Status:           CrashLoopBackOff\n"
        "Restarts:         3\n"
        "Conditions:\n"
        "  Type           Status  Reason\n"
        "  ---           ------  ------\n"
        "  Initialized    True    True\n"
        "  Ready          False   ContainersNotReady\n"
        "Events:\n"
        "  Type     Reason     Age   From               Message\n"
        "  ----     ------     ---   ----               -------\n"
        "  Normal   Pulled     45m   kubelet            Successfully pulled image\n"
        "  Warning  BackOff    30s   kubelet            Back-off restarting failed container\n"
    ),
    "ml-training-job": (
        "Name:             ml-training-job-4f5g6h7j8k-q2w3e\n"
        "Namespace:        ml\n"
        "Status:           Error\n"
        "Restarts:         7\n"
        "Conditions:\n"
        "  Type           Status  Reason\n"
        "  ---           ------  ------\n"
        "  Initialized    True    True\n"
        "  Ready          False   ContainersNotReady\n"
        "Events:\n"
        "  Type     Reason          Age   From               Message\n"
        "  ----     ------          ---   ----               -------\n"
        "  Normal   Pulled          2h    kubelet            Container image already present\n"
        "  Normal   Created         2h    kubelet            Created container\n"
        "  Warning  BackOff         10m   kubelet            Back-off restarting failed container\n"
    ),
    "analytics-etl": (
        "Name:             analytics-etl-9a8b7c6d5e-r4t5y\n"
        "Namespace:        analytics\n"
        "Status:           ImagePullBackOff\n"
        "Restarts:         0\n"
        "Conditions:\n"
        "  Type           Status  Reason\n"
        "  ---           ------  ------\n"
        "  Initialized    True    True\n"
        "  Ready          False   ContainersNotReady\n"
        "Events:\n"
        "  Type     Reason          Age   From               Message\n"
        "  ----     ------          ---   ----               -------\n"
        "  Normal   BackOff         9m    kubelet            Back-off pulling image\n"
        "  Warning  Failed          1m    kubelet            Error: ImagePullBackOff\n"
        '  Normal   Pulling         30s   kubelet            Pulling image "analytics/etl:latest"\n'
        "  Warning  Failed          28s   kubelet            Failed to pull image: manifest not found\n"
    ),
    "cache-redis": (
        "Name:             cache-redis-2f4g6h8j0k-m3n4b\n"
        "Namespace:        cache\n"
        "Status:           Pending\n"
        "Restarts:         0\n"
        "Conditions:\n"
        "  Type           Status  Reason\n"
        "  ---           ------  ------\n"
        "  Initialized    True    True\n"
        "  Ready          False   ContainersNotReady\n"
        "  PodScheduled   False   Unschedulable\n"
        "Events:\n"
        "  Type     Reason            Age   From               Message\n"
        "  ----     ------            ---   ----               -------\n"
        "  Warning  FailedScheduling  5m    default-scheduler  0/3 nodes are available: 3 Insufficient cpu.\n"
    ),
    "recommend-engine": (
        "Name:             recommend-engine-d3f5g7h9j1-v2c4x\n"
        "Namespace:        ml\n"
        "Status:           OOMKilled\n"
        "Restarts:         12\n"
        "Conditions:\n"
        "  Type           Status  Reason\n"
        "  ---           ------  ------\n"
        "  Initialized    True    True\n"
        "  Ready          False   ContainersNotReady\n"
        "Events:\n"
        "  Type     Reason          Age   From               Message\n"
        "  ----     ------          ---   ----               -------\n"
        "  Normal   Started         55m   kubelet            Started container\n"
        "  Warning  OOMKilling      22m   kubelet            Memory cgroup out of memory: killed process\n"
        "  Normal   Pulled          17m   kubelet            Container image already present\n"
    ),
}


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
    for key, desc in _MOCK_DESCRIBE.items():
        if key in name:
            return f"(mock) kubectl describe pod {name} -n {namespace}\n\n{desc}"
    return f"(mock) kubectl describe pod {name} -n {namespace}"


_MOCK_LOGS = {
    "payment-processor": (
        "2026-07-14 12:01:03 [ERROR] [payment_processor.py:45] connection to upstream timeout after 30s\n"
        "2026-07-14 12:01:03 [ERROR] [payment_processor.py:46] Transaction ID: tx-7f3a9c2e — status: PENDING\n"
        "2026-07-14 12:01:04 [CRITICAL] [main.py:22] Circuit breaker tripped: payment gateway unreachable\n"
        "2026-07-14 12:01:04 [INFO] [main.py:25] Pod will exit and restart in CrashLoopBackOff\n"
    ),
    "ml-training-job": (
        "2026-07-14 10:30:01 [INFO] [train.py:15] Loading dataset...\n"
        "2026-07-14 10:30:02 [ERROR] [train.py:17] OSError: [Errno 28] No space left on device\n"
        "2026-07-14 10:30:02 [ERROR] [train.py:18] Cannot write checkpoint to /data/models/checkpoint.pt\n"
        "2026-07-14 10:30:03 [CRITICAL] [main.py:42] Training failed — disk full\n"
    ),
    "analytics-etl": ("Container is waiting to pull image.\n" "No logs available.\n"),
    "payment-worker": (
        "Traceback (most recent call last):\n"
        '  File "/app/main.py", line 12, in process_payment\n'
        "    from workers.payment import PaymentProcessor\n"
        "ModuleNotFoundError: No module named 'workers'\n"
    ),
    "monitoring-agent": (
        "Error: failed to get image manifest: unknown flag: --platform\n"
        "Usage:  docker pull [OPTIONS] NAME[:TAG|@DIGEST]\n"
        "The agent is using a deprecated Docker CLI flag.\n"
    ),
    "analytics-job": ("Container is still waiting to start.\n" "No logs available.\n"),
    "cache-redis": ("Container is still waiting to start.\n" "No logs available.\n"),
    "recommend-engine": (
        "2026-07-14 10:55:01 [INFO] [server.py:8] Loading model into memory...\n"
        "2026-07-14 10:55:03 [INFO] [server.py:12] Model loaded successfully\n"
        "2026-07-14 10:55:05 [ERROR] [server.py:15] Memory allocation failed: std::bad_alloc\n"
        "2026-07-14 10:55:06 [CRITICAL] [server.py:16] Out of memory — model too large for container\n"
    ),
}


def get_logs(name: str, namespace: str = "default") -> str:
    """Get pod logs for debugging crashes."""
    if _has_kubectl() and _cluster_reachable():
        result = subprocess.run(
            ["kubectl", "logs", name, "-n", namespace, "--tail=50"],
            capture_output=True,
            text=True,
        )
        return result.stdout or result.stderr

    for key, log in _MOCK_LOGS.items():
        if key in name:
            return f"(mock) kubectl logs {name} -n {namespace}\n\n{log}"
    return f"(mock) kubectl logs {name} -n {namespace}\n\n(no recent logs)"
