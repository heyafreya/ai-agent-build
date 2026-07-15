import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Query  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from src.agent import analyze_with_alerts  # noqa: E402
from src.alerts import score_pod, severity_counts  # noqa: E402
from src.k8s_client import get_pods, set_scenario  # noqa: E402
from uvicorn import run  # noqa: E402

app = FastAPI(title="K8s Health Monitor")


@app.get("/health")
def health(scenario: str = Query("composite")):
    """Deterministic pod health summary — no LLM call."""
    set_scenario(scenario)
    pods = get_pods()
    counts = severity_counts(pods)
    pod_list = []
    for p in pods:
        pod_list.append(
            {
                "name": p.name,
                "namespace": p.namespace,
                "status": p.status,
                "restarts": p.restarts,
                "ready": p.ready,
                "severity": score_pod(p),
            }
        )
    pod_list.sort(key=lambda x: {"critical": 0, "warning": 1, "healthy": 2}[x["severity"]])
    return {"counts": counts, "pods": pod_list}


@app.get("/pods")
def pods(scenario: str = Query("composite")):
    """Return just the pod list for populating the dropdown."""
    set_scenario(scenario)
    pods_data = get_pods()
    return [{"name": p.name, "namespace": p.namespace, "status": p.status} for p in pods_data]


@app.get("/analyze")
async def analyze(scenario: str = Query("composite"), pod: str = Query(None)):
    """LLM-powered analysis — runs in thread pool to avoid blocking."""
    set_scenario(scenario)
    result = await asyncio.to_thread(analyze_with_alerts, focus_pod=pod)
    return {"result": result}


@app.get("/scenarios")
def scenarios():
    return {
        "scenarios": [
            "composite",
            "healthy",
            "crashing",
            "solo-crashloop",
            "solo-error",
            "solo-oom",
            "solo-pending",
            "solo-imagepull",
        ]
    }


app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")

if __name__ == "__main__":
    run(app, host="127.0.0.1", port=8080)
