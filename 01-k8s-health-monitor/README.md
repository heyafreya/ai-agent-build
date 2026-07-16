# K8s Health Monitor Agent

An AI agent that monitors a Kubernetes cluster and summarizes pod health in plain English.

## Table of Contents

- [How This Project Was Built](#how-this-project-was-built)
- [Learning Journal: Agent Design Foundations](#learning-journal-agent-design-foundations)
- [Learning Journal: Concepts Learned](#learning-journal-concepts-learned)
- [Web UI: Session Learnings & Challenges](#web-ui-session-learnings--challenges)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Roadmap](#roadmap)

---

## How This Project Was Built

This project was created using:

- **ChatGPT** — to explore ideas and decide which agent to build for a competition
- **Opencode** (CLI coding agent) — to scaffold the project, write code, and explain concepts interactively

The workflow was: brainstorm with ChatGPT → plan with Opencode → implement with Opencode, asking questions along the way to learn each concept before writing code. This README documents everything learned during the process.

---

## Learning Journal: Agent Design Foundations

In its most fundamental form, an agent consists of three core components:

### Model
The LLM powering the agent's reasoning and decision-making. This is the "brain." It can be any model — GPT-4, Claude, Gemini, a local Llama — accessed through an API.

In this project, the model is abstracted behind `litellm` so we can swap providers by changing one environment variable.

### Tools
External functions or APIs the agent can use to take action. Without tools, an LLM can only produce text — with tools, it can query databases, run commands, send emails, etc.

In this project, the tools are:
- `k8s_client.get_pods()` — collects pod status data from the cluster
- `k8s_client.describe_pod()` — gets detailed pod info for debugging

### Instructions
Explicit guidelines and guardrails defining how the agent behaves. This is the system prompt — it tells the agent what to do, how to format output, and what rules to follow.

In this project, the system prompt is defined in `src/agent.py:SYSTEM_PROMPT`. It tells the agent to:
1. Summarize overall cluster health
2. List unhealthy pods with causes and actions
3. Give a health score
4. Never hallucinate data

### The Agent Loop

```
1. User request comes in (via CLI)
2. Agent collects data using its tools (k8s_client)
3. Agent formats data and sends it to the Model (LLM) with Instructions
4. Model returns a response in the specified format
5. Response is displayed to the user
```

This is the simplest form of an agent. More advanced agents let the LLM choose which tools to call (ReAct pattern), call tools in sequence, or loop until a goal is met.

---

## Learning Journal: Concepts Learned

### 1. What is an LLM API?

An LLM API lets you send text to a model and get text back. The basic call is:

```
POST /v1/completions
{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Summarize this data: ..."}
  ]
}
```

The `system` message sets behavior, the `user` message is the input. The model returns `assistant` content.

### 2. litellm — multi-provider LLM client

**What it is**: A Python library that provides a unified interface to 100+ LLM providers (OpenAI, Anthropic, Google Gemini, Groq, Ollama, OpenRouter, AWS Bedrock, Azure, etc.).

**Why it matters**: Without litellm, switching from OpenAI to Anthropic means rewriting all your API calls. With litellm, you change the `model` string:

```python
# Same code, different provider:
litellm.completion(model="gemini/gemini-2.0-flash-exp", messages=[...])
litellm.completion(model="groq/llama3-70b-8192", messages=[...])
litellm.completion(model="ollama/llama3.2", messages=[...])
```

**Free providers available through litellm**:
- **Google Gemini** — 60 requests/minute free tier
- **Groq** — fast inference, free tier with rate limits
- **Ollama** — run models locally on your machine, completely free
- **OpenRouter** — has free models + pay-as-you-go access

### 3. subprocess — running terminal commands from Python

**What it is**: Python's `subprocess` module lets you run any command you could type in a terminal and capture its output.

```python
import subprocess
result = subprocess.run(["kubectl", "get", "pods", "-A"], capture_output=True, text=True)
print(result.stdout)  # The command output
```

**Why use it instead of the Kubernetes Python SDK?**
- No authentication setup — uses your existing `kubeconfig`
- Simpler for read-only operations
- The SDK requires the same `kubeconfig` anyway, so no real advantage

For this project, we check if `kubectl` is available and a cluster is reachable. If not, we fall back to mock data — perfect for development.

### 4. kubectl — the Kubernetes CLI

**What it is**: `kubectl` is the command-line tool for interacting with Kubernetes clusters. It reads from `~/.kube/config` to find cluster connection details.

**Key commands we use**:
- `kubectl get pods -A -o json` — list all pods across all namespaces in JSON
- `kubectl describe pod <name> -n <namespace>` — detailed info including events

**Getting a cluster for development**:
- **Kind** (Kubernetes in Docker) — runs a local cluster on your machine
- **Minikube** — another local cluster option
- **Docker Desktop** — has built-in K8s support
- **Cloud clusters** — EKS, GKE, AKS (free tiers available)

### 5. Typer — CLI framework for Python

**What it is**: A library for building CLI applications using Python type hints. Built on top of Click.

```python
import typer

app = typer.Typer()

@app.command()
def health(namespace: Optional[str] = typer.Option(None, "--namespace")):
    """Analyze pod health."""
    ...

if __name__ == "__main__":
    app()
```

Typer auto-generates `--help` text from docstrings and type annotations. No manual argument parsing needed.

### 6. Rich — beautiful terminal output

**What it is**: A library for rich text formatting in the terminal — colors, tables, markdown rendering, progress bars, etc.

We use `rich.markdown.Markdown` to render the LLM's markdown-formatted response directly in the terminal.

### 7. Pydantic — data validation

**What it is**: A library for defining data models with type validation. Ensures the data we collect from the cluster is well-typed.

```python
class PodInfo(BaseModel):
    name: str
    namespace: str
    status: str
    restarts: int
```

### 8. The Model-Tools-Instructions Pattern in practice

Here's how the three agent components map to files in this project:

```
┌─────────────────────────────────────────────────────────────┐
│                      K8s Health Agent                        │
├───────────────┬─────────────────────┬───────────────────────┤
│    Model      │       Tools         │     Instructions       │
├───────────────┼─────────────────────┼───────────────────────┤
│ shared/llm.py │ src/k8s_client.py   │ src/agent.py           │
│               │                     │  SYSTEM_PROMPT         │
│ litellm talks │ get_pods()          │                       │
│ to any LLM    │ describe_pod()      │ "Summarize pod health  │
│ provider      │                     │  in plain English..."  │
└───────────────┴─────────────────────┴───────────────────────┘
```

### 9. Kubernetes Pod Lifecycle

Key pod statuses an agent needs to understand:

| Status | Meaning |
|--------|---------|
| **Running** | Pod is running normally |
| **Pending** | Pod hasn't started yet (scheduling, pulling image, etc.) |
| **CrashLoopBackOff** | Container keeps crashing and restarting — serious |
| **ImagePullBackOff** | Can't pull the container image — wrong name, no access, or registry issue |
| **Completed** | Job finished successfully |
| **Error** | Container exited with error code |

### 10. Environment Variables / dotenv

**What it is**: A pattern for managing configuration outside of code. API keys, model names, and settings are read from environment variables.

`.env` files store these locally (never commit them!). `python-dotenv` loads them automatically.

---

## Web UI: Session Learnings & Challenges

### July 12, 2026 — Agent Design Foundations

Read [A Practical Guide to Building AI Agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/) (OpenAI) before starting implementation.

**Core insight**: An agent is not just an LLM — it's three components working together:

- **Model**: The LLM powering reasoning and decision-making. This is the "brain." Can be GPT-4, Claude, Gemini, Llama — anything accessible via API.
- **Tools**: External functions or APIs the agent can call to take action. Without tools, an LLM can only produce text. With tools, it can query databases, run commands, send emails, read files, etc.
- **Instructions**: Explicit guidelines and guardrails defining how the agent behaves. The system prompt — it tells the agent what to do, how to format output, and what rules to follow.

This framework shaped how `agent.py` was built: `shared/llm.py` is the Model, `src/k8s_client.py` provides the Tools, and `src/agent.py:SYSTEM_PROMPT` defines the Instructions.

Reference: OpenAI's Agents SDK implements the same pattern. You can also build it from scratch with any LLM library.

---

### July 13, 2026 — Kubernetes Knowledge Refresh

Relearned core Kubernetes concepts needed for this project:

**A Kubernetes Pod** is the smallest deployable unit in Kubernetes that runs one or more application containers. Pods provide an abstraction layer that includes:

- Shared storage volumes
- A single IP address shared by all containers in the pod
- Inter-container communication over localhost
- Host-level information for running containers

This architecture allows closely related containers to communicate efficiently while maintaining isolation from other pods.

**Key pod statuses** the agent needs to understand:

| Status | Meaning |
|--------|---------|
| Running | Pod is operating normally |
| Pending | Not yet started (scheduling, pulling image) |
| CrashLoopBackOff | Container keeps crashing and restarting |
| ImagePullBackOff | Can't pull the container image |
| Completed | Job finished successfully |
| Error | Container exited with error code |

This knowledge directly informed the severity scoring logic in `alerts.py` and the tool design in `k8s_client.py`.

---

### July 14, 2026 — Web UI Build

### What Was Built

Transformed the CLI agent into a local web interface with three tabs: **Projects** (summary), **Live Demo** (interactive analysis), and **Model Comparison** (future). The Live Demo tab runs the ReAct agent against mock K8s clusters with a pod dropdown, severity charts, namespace breakdown, and an LLM-generated analysis rendered as markdown.

### Key Fixes & Discoveries

**1. Composite Caching Bug — Root Cause of LLM Hallucinations**

The LLM kept inventing pod names like `frontend-abc123` and `payment-service`. The root cause: `_build_composite_scenario()` uses `random.sample()` to randomly select pods from the pool. Each call to `get_pods()` generated a different set, so the agent would describe pods in one call that didn't exist in the next.

Fix: Added `_composite_cache` dict in `k8s_client.py` — the first call stores the result, subsequent calls return the cached set. Cache is cleared on `set_scenario()`.

**2. LLM Hallucination — Missing Pod Context**

Even after fixing the cache, the LLM sometimes described pods that weren't in the scenario. Fix: Added `EXISTING PODS` list directly in the system prompt so the LLM can only reference real pods.

**3. Health Score "Degraded" on Healthy Clusters**

The LLM would sometimes score a fully healthy cluster as "Degraded." Fix: Added explicit scoring rules to the prompt — e.g., "if ALL pods Running with restarts < 3 and full ready ratios → MUST be Healthy."

**4. Pod Focus Skipping GET\_PODS**

When a user selects a single pod, the agent was still listing all pods first, exposing unhealthy ones that the LLM would then investigate. Fix: When `focus_pod` is set, the agent skips `GET_PODS` entirely and goes straight to `DESCRIBE_POD` on the focused pod.

**5. Charts Showing All Pods in Focus Mode**

Severity chart and namespace breakdown always showed all 6 pods even when one was focused. Fix: Client-side filtering — when a pod is selected, `healthData.pods` is filtered to only that pod before rendering charts.

**6. Missing Mock Data for Healthy Pods**

`describe_pod()` only had mock data for the 5 bad pods. Healthy pods returned a generic empty message, so the LLM invented CrashLoopBackOff. Fix: Added detailed mock `kubectl describe` output for all 6 healthy pods (web-frontend, api-gateway, user-service-db, auth-service, nginx-deploy, cron-job-scheduler).

**7. Markdown Regex Couldn't Handle LLM Output**

The LLM outputs full markdown (`##`, `###`, `- **bold**:`), but chained regex replacements couldn't parse it. Fix: Replaced the regex pipeline with `marked.js` via CDN.

**8. Pod Table Text Color Inheritance**

Table cells inherited `color: var(--text-secondary)` from `#output`, making them grey. Fix: Explicit `color: var(--text)` on `.pod-table td`.

**9. JS Regex Order Bug**

`##` was replaced before `###`, so `### Issues Found` became `##Issues Found` (wrong). Fix: Reverse the order — `###` first, then `##`.

### Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| `marked.js` over regex chains | LLM outputs complex markdown — regex can't reliably parse nested headings, bold, lists |
| Charts in analysis output (not separate card) | User wanted a single analysis block — removing the Health Summary card |
| `max_iterations` 6 → 8 | Agent needs more steps in composite scenarios with multiple unhealthy pods |
| Composite cache | `random.sample()` is non-deterministic — caching ensures consistency across endpoints |

### What I Learned

- **LLMs are pattern matchers, not truth-tellers.** Without explicit pod lists and scoring rules, the model invents plausible-sounding but fabricated data.
- **Caching is critical when data is randomly generated.** A single `random.sample()` call per request is fine; multiple calls with no shared state causes drift.
- **Focus mode requires filtering at every layer.** Selecting a pod isn't just about the API call — charts, tables, and LLM context all need to respect the focus.
- **Mock data completeness matters.** If you only mock failure cases, the LLM will assume everything is failing.
- **Client-side state management is easy to overlook.** The `/health` endpoint returns all pods regardless of focus — the client must filter before rendering.

---

## Quick Start

```bash
# From the repo root:

# Install dependencies (requires uv — https://docs.astral.sh/uv/)
make install

# Configure your LLM provider
cp .env.example .env
# Edit .env — add your API key (Gemini free tier works: https://aistudio.google.com/apikey)

# Run the CLI
make run

# Or run the web UI
make serve
# Open http://localhost:8080
```

No Kubernetes cluster needed — the agent uses realistic mock data by default. It auto-detects a live cluster if `kubectl` can reach one.

---

## Usage

### CLI

```bash
# Default analysis (composite scenario with random bad pods)
uv run python -m 01-k8s-health-monitor.src.cli

# Specific scenario
uv run python -m 01-k8s-health-monitor.src.cli -s solo-oom

# Filter by namespace
uv run python -m 01-k8s-health-monitor.src.cli -n default

# Watch mode — re-analyze every 30 seconds
uv run python -m 01-k8s-health-monitor.src.cli -w
```

Available scenarios: `healthy`, `crashing`, `composite`, `solo-crashloop`, `solo-error`, `solo-imagepull`, `solo-pending`, `solo-oom`

### Web UI

```bash
make serve
# Open http://localhost:8080
```

| Tab | Features |
|-----|----------|
| **Projects** | Architecture docs, component reference, learning notes |
| **Live Demo** | Scenario/pod dropdowns, severity charts, namespace breakdown, agent trace (expandable), chat follow-up |
| **Model Comparison** | Run same scenario across multiple models, side-by-side latency/tokens/accuracy cards |
| **Evaluation** | Score agent against 6 ground-truth scenarios, pass/fail scorecard |

---

## How Model Comparison Works

The Model Comparison tab runs the **same scenario** across multiple LLM providers and shows results side-by-side. Here's the flow:

1. **User picks a scenario** (e.g. `solo-oom`, `composite`) and clicks "Compare Models"
2. **Backend runs the agent in parallel** using `ThreadPoolExecutor` — one thread per model. Each thread calls `agent.analyze()` with a different `model` parameter (e.g. `gemini/gemini-2.0-flash-exp`, `openai/gpt-4o-mini`, `anthropic/claude-3-5-haiku-20241022`, `ollama/llama3.2:3b`)
3. **Each model gets the same prompt, same tools, same mock data.** The only variable is the model itself.
4. **Results are collected** with per-model metadata: latency (ms), token counts, health score assigned, number of issues found, full analysis text, and the complete agent trace.
5. **UI renders comparison cards** sorted by latency (fastest first), each showing metrics and a truncated analysis with "Show full output" expandable.

**What you can compare:**

| Metric | What it tells you |
|--------|-------------------|
| Latency | How fast each model produces an analysis |
| Token usage | Cost proxy (more tokens = more expensive) |
| Health score | Whether the model correctly identifies Critical/Degraded/Healthy |
| Issue count | How many problems the model found |
| Full output | Quality and specificity of root causes and fixes |
| Agent trace | How many tool calls each model needed, where it got confused |

**Models included by default:**

| Model | Provider | Notes |
|-------|----------|-------|
| `gemini/gemini-2.0-flash-exp` | Google | Free tier, fast |
| `openai/gpt-4o-mini` | OpenAI | Cheap, good quality |
| `anthropic/claude-3-5-haiku-20241022` | Anthropic | Fast, high quality |
| `ollama/llama3.2:3b` | Local | Free, runs on your machine |
| `ollama/mistral:7b` | Local | Free, larger local model |

**Requirements:** Add API keys for the providers you want to compare to `.env`. Ollama models work locally if you have `ollama serve` running.

---

## Project Structure

```
01-k8s-health-monitor/
├── src/
│   ├── __init__.py
│   ├── cli.py             # CLI entry point (Typer)
│   ├── agent.py           # ReAct agent loop + trace capture + chat follow-up
│   ├── alerts.py          # Deterministic severity scoring (LLM-independent)
│   ├── k8s_client.py      # Pod collector with mock fallback
│   ├── comparison.py      # Multi-model parallel comparison
│   └── eval.py            # Evaluation framework with ground-truth scoring
├── web/
│   ├── index.html         # 4-tab layout (Projects, Live Demo, Comparison, Eval)
│   ├── script.js          # Charts, trace rendering, comparison grid, chat
│   └── style.css          # Clean minimal design + component styles
├── server.py              # FastAPI server (/health, /pods, /analyze, /chat, /compare, /eval)
├── pyproject.toml         # Dependencies (fastapi, uvicorn, litellm, etc.)
├── .env                   # API keys and model config (not committed)
└── README.md
```

---

## Configuration

See `.env.example` for all config options:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_MODEL` | `gemini/gemini-2.0-flash-exp` | Full model identifier for litellm |
| `GEMINI_API_KEY` | — | Your Gemini API key (free tier) |
| `OPENAI_API_KEY` | — | Your OpenAI API key (for comparison) |
| `ANTHROPIC_API_KEY` | — | Your Anthropic API key (for comparison) |
| `GROQ_API_KEY` | — | Your Groq API key |

For model comparison, add API keys for the providers you want to benchmark. The default analysis only needs one provider (Gemini free tier works).

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health?scenario=composite` | GET | Deterministic pod health (no LLM call) |
| `/pods?scenario=composite` | GET | Pod list for UI dropdown |
| `/analyze?scenario=composite&pod=<name>&model=<id>` | GET | Full agent analysis with trace |
| `/chat` | POST | Follow-up chat (`{message, conversation_id}`) |
| `/compare` | POST | Multi-model comparison (`{scenario, models?}`) |
| `/eval` | POST | Evaluation scorecard (`{model?}`) |
| `/models` | GET | List available comparison models |
| `/scenarios` | GET | List available mock scenarios |

---

## Roadmap

- [x] Alert thresholds (deterministic severity scoring)
- [x] Web UI with interactive demo
- [x] Structured JSON output (reliable tool parsing)
- [x] Agent trace capture + debug view
- [x] Model comparison (multi-provider benchmarking)
- [x] Evaluation framework (ground-truth scoring)
- [x] Chat follow-up (interactive investigation)
- [ ] Support `--output json` for machine-readable output
- [ ] Add Slack/email notifications for unhealthy pods
- [ ] Add historical analysis — track health over time
- [ ] Support filtering by label selectors
- [ ] Deploy as a Kubernetes CronJob that posts to a channel
- [ ] Streaming responses (real-time agent thinking in web UI)
- [ ] Additional tools: GET_EVENTS, GET_DEPLOYMENTS, GET_RESOURCE_QUOTA
- [ ] Persistent conversation store (SQLite instead of in-memory)
- [ ] More eval cases (multi-pod cascading failures, namespace isolation)
