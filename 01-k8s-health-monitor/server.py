import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Query  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from src.agent import analyze, chat_follow_up  # noqa: E402
from src.alerts import score_pod, severity_counts  # noqa: E402
from src.comparison import compare_models, get_model_label  # noqa: E402
from src.eval import run_eval  # noqa: E402
from src.k8s_client import get_pods, set_scenario  # noqa: E402
from uvicorn import run  # noqa: E402

app = FastAPI(title="K8s Health Monitor")

# ── In-memory conversation store ───────────────────────────────────
_conversations: dict[str, list[dict]] = {}


# ── Existing endpoints (enhanced) ──────────────────────────────────


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
async def analyze_endpoint(
    scenario: str = Query("composite"),
    pod: str = Query(None),
    model: str = Query(None),
):
    """LLM-powered analysis — returns result + trace + conversation_id."""
    set_scenario(scenario)
    result, trace = await asyncio.to_thread(analyze, focus_pod=pod, model=model, scenario=scenario)
    _conversations[trace.conversation_id] = [{"role": "assistant", "content": result}]
    return {
        "result": result,
        "trace": trace.model_dump(),
        "conversation_id": trace.conversation_id,
    }


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


# ── Chat follow-up endpoint ────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    model: str | None = None


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """Continue a conversation about pod health."""
    history = _conversations.get(req.conversation_id, [])
    response, updated_history = await asyncio.to_thread(
        chat_follow_up, req.message, history, req.conversation_id, req.model
    )
    _conversations[req.conversation_id] = updated_history
    return {"response": response, "conversation_id": req.conversation_id}


# ── Model comparison endpoint ──────────────────────────────────────


class CompareRequest(BaseModel):
    scenario: str = "composite"
    pod: str | None = None
    models: list[str] | None = None


@app.post("/compare")
async def compare_endpoint(req: CompareRequest):
    """Run the same scenario across multiple models in parallel."""
    results = await asyncio.to_thread(compare_models, None, req.pod, req.scenario, req.models)
    return {
        "results": [
            {
                "model": r.model,
                "label": get_model_label(r.model),
                "answer": r.answer,
                "trace": r.trace.model_dump(),
                "latency_ms": r.latency_ms,
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "health_score": r.health_score,
                "issue_count": r.issue_count,
                "error": r.error,
            }
            for r in results
        ]
    }


# ── Evaluation endpoint ────────────────────────────────────────────


class EvalRequest(BaseModel):
    model: str | None = None


@app.post("/eval")
async def eval_endpoint(req: EvalRequest):
    """Run the evaluation suite and return a scorecard."""
    report = await asyncio.to_thread(run_eval, req.model)
    return report.model_dump()


# ── Available models endpoint ──────────────────────────────────────


@app.get("/models")
def available_models():
    """Return the list of models available for comparison."""
    from src.comparison import COMPARISON_MODELS

    return {"models": [{"id": m[0], "label": m[1]} for m in COMPARISON_MODELS]}


# ── Static files ───────────────────────────────────────────────────

app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")

if __name__ == "__main__":
    run(app, host="127.0.0.1", port=8080)
