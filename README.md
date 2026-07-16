# ai-agent-build

My entry for the **Boston Kubernetes Meetup AI Agent Build Competition** — a skills-building competition where the goal isn't to build the fanciest agent, it's to practice a new skill, document what you learned, and publish it so others can learn too.

I hadn't built an agent before and don't have extensive Kubernetes experience. This project let me learn both at the same time by building something real: an AI agent that monitors a Kubernetes cluster and explains what's wrong in plain English.

---

## What I Built

An AI agent that investigates pod health and produces actionable summaries. Give it a cluster (or use the built-in mock data) and it will:

1. List all pods and identify the unhealthy ones
2. Investigate each failure by pulling logs and descriptions
3. Explain the root cause and suggest a fix
4. Score severity with deterministic rules (independent of the LLM)

Run it from the CLI or open the web UI — there's a Live Demo tab, Model Comparison tab (benchmark different LLMs side-by-side), and an Evaluation tab that scores the agent's accuracy.

## How to Run

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc

# Setup
git clone <repo-url>
cd ai-agent-build
make install

# Configure an LLM (Gemini free tier works)
cp .env.example .env
# Edit .env — add your API key

# CLI
make run

# Web UI
make serve
# Open http://localhost:8080
```

No Kubernetes cluster needed — mock data is built in. The agent auto-detects a live cluster if `kubectl` can reach one.

## What I Learned

**The Model-Tools-Instructions pattern.** An agent isn't just an LLM — it's a model (the brain), tools (what it can do), and instructions (how it behaves). The system prompt is where most of the agent's personality and reliability comes from.

**LLMs fabricate data without guardrails.** Without an explicit pod list in the prompt, the model invents pod names that don't exist. Adding `EXISTING PODS` to the system prompt fixed this — the agent can only reference real pods.

**Deterministic scoring as a safety net.** LLMs aren't deterministic — the same input can produce different outputs. I added a pure-function severity scorer (`alerts.py`) that runs alongside the LLM. No matter what the model says, the severity block underneath is computed from hard rules.

**Regex parsing is fragile.** The original agent used regex to parse tool calls from freeform LLM text. Any markdown formatting broke it. Switching to structured JSON output made the agent reliable.

**Traces make agents transparent.** Capturing every step of the ReAct loop — what the LLM saw, what it decided, what tools returned — turns a black box into something you can debug and trust.

**Mock data must cover success cases.** I only mocked failure scenarios at first. The LLM assumed everything was broken and invented issues for healthy pods. Adding realistic healthy mock data fixed this.

## Architecture

```
CLI / Web UI
    |
    v
agent.py (ReAct loop)
    |--- k8s_client.py ---> [kubectl] or [mock data]
    |--- LLM decides: GET_PODS, GET_LOGS, DESCRIBE_POD
    |--- alerts.py ---------> deterministic severity scores
    |
    v
Combined output: LLM analysis + severity block + trace data
```

## Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| LLM client | litellm | Swap providers by changing one env var |
| K8s data | subprocess + kubectl | Zero config, auto-detects cluster vs mock |
| Agent loop | Custom ReAct | LLM decides which tools to call, iterates until done |
| Server | FastAPI | Simple async server for the web UI |
| Package mgmt | uv | Fast installs, deterministic lockfile |

## Repo Structure

```
├── 01-k8s-health-monitor/
│   ├── src/
│   │   ├── agent.py           # ReAct agent loop + trace capture
│   │   ├── k8s_client.py      # Pod collector with mock fallback
│   │   ├── alerts.py          # Deterministic severity scoring
│   │   ├── comparison.py      # Multi-model benchmarking
│   │   ├── eval.py            # Evaluation framework
│   │   └── cli.py             # CLI entry point
│   ├── web/                   # Web UI (HTML/JS/CSS)
│   └── server.py              # FastAPI server
├── shared/llm.py              # LiteLLM wrapper
├── Makefile
└── pyproject.toml
```

---

## Build Journal

<details>
<summary><strong>Jul 13</strong> — Scaffold + first agent</summary>

Built the project structure, implemented `k8s_client.py` (pod data collector with mock fallback), `agent.py` (one-shot LLM call), `cli.py` (Typer CLI), and `shared/llm.py` (litellm wrapper). Learned the Model-Tools-Instructions pattern from OpenAI's agent design guide.

</details>

<details>
<summary><strong>Jul 14</strong> — ReAct loop + scenarios</summary>

Replaced the one-shot LLM call with a ReAct loop — the agent now iterates, calling `GET_LOGS` and `DESCRIBE_POD` on its own until it has enough evidence. Added 5 solo error scenarios and a composite mode that randomly mixes healthy + unhealthy pods.

</details>

<details>
<summary><strong>Jul 14</strong> — Tooling + alert thresholds</summary>

Switched to uv for package management, added pre-commit hooks (ruff + conventional commits). Built `alerts.py` — deterministic severity scoring independent of the LLM. Wired it into the agent as a "belt and suspenders" safety net.

</details>

<details>
<summary><strong>Jul 14</strong> — Web UI</summary>

Built a FastAPI server with a 3-tab web interface: Projects (docs), Live Demo (interactive analysis with charts), and Model Comparison (placeholder). Fixed several hallucination bugs — the LLM kept inventing pod names that didn't exist.

</details>

<details>
<summary><strong>Jul 15</strong> — Structured output + trace capture</summary>

Replaced fragile regex tool parsing with structured JSON output. Every ReAct iteration is now captured as a `TraceStep` — what the LLM saw, what it decided, what the tool returned, latency, tokens. The agent went from occasionally failing silently to reliably parsing every tool call.

</details>

<details>
<summary><strong>Jul 15</strong> — Model comparison + evaluation</summary>

Built a comparison engine that runs the same scenario across Gemini, GPT-4o Mini, Claude, and Ollama models in parallel. Built an evaluation framework with 6 ground-truth test cases that scores severity accuracy, root cause recall, and hallucination rate.

</details>

<details>
<summary><strong>Jul 15</strong> — Chat follow-up + debug view</summary>

Added interactive chat — after the initial analysis, users can ask follow-up questions like "How do I fix this?" The agent maintains context and can investigate further. Added an expandable Agent Trace panel showing every step of the reasoning process.

</details>
