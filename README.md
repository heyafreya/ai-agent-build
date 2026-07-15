# ai-agent-build

A collection of agentic AI projects, exploring the **Model → Tools → Instructions** pattern for practical infrastructure and developer workflows.

Built interactively using **ChatGPT** for design exploration and **Opencode** for scaffold + implementation.

---

## Journal

<details>
<summary><strong>2026-07-13</strong> — K8s Health Monitor: scaffold + agent loop</summary>

### What was done

- Scaffolded the `01-k8s-health-monitor/` project with full source layout
- Implemented `k8s_client.py` — pod data collector using `subprocess` + `kubectl` with automatic mock fallback (10 realistic pods across statuses: Running, CrashLoopBackOff, Pending, ImagePullBackOff)
- Implemented `agent.py` — core agent wiring: collects pod data → formats as table → sends to LLM with a system prompt → returns plain-English health summary
- Implemented `cli.py` — Typer CLI with `--namespace`, `--describe`, `--watch` flags
- Created `shared/llm.py` — litellm-based LLM client supporting Gemini free tier, Groq, Anthropic, OpenAI, Ollama, and 100+ providers
- Documented all learning in the subproject README: agent design foundations, litellm, subprocess, kubectl, kubepod lifecycle, typer, pydantic, rich

### Key decisions

| Decision        | Choice               | Rationale                                                                         |
| --------------- | -------------------- | --------------------------------------------------------------------------------- |
| LLM abstraction | litellm              | Swap providers by changing one env var; Gemini free tier for dev, Claude for prod |
| K8s interaction | subprocess + kubectl | Zero config overhead; no SDK auth to set up; auto-detects cluster vs mock         |
| CLI framework   | typer                | Type-hint driven, auto --help, minimal boilerplate                                |
| Data modeling   | pydantic             | Type-safe PodInfo models with zero-effort validation                              |
| Terminal output | rich                 | Markdown rendering of LLM responses directly in terminal                          |

### Questions answered

- **OpenAI vs Anthropic?** Both work. Claude is better at structured output for multi-pod analysis. litellm makes swapping trivial.
- **Do I need a cluster?** No — mock data is built in for dev. Switch to live by installing Kind or pointing at any cluster.
- **Is this free?** Yes — Gemini free tier (60 req/min) or Ollama (local, no API key).
- **subprocess vs K8s SDK?** subprocess is simpler for read-only queries. SDK adds complexity without benefit for this use case.

</details>
<details>
<summary><strong>2026-07-14</strong> — ReAct agent loop + mock scenarios</summary>

### What was done

- Replaced one-shot LLM call with a **ReAct loop**: agent calls `GET_LOGS` and `DESCRIBE_POD` iteratively, deciding which tool to use based on pod state
- Added `get_logs()` to `k8s_client.py` with mock logs for each failure type (ModuleNotFoundError, OOM, disk full, network timeout, image pull failure)
- Added 5 solo error scenarios (`solo-crashloop`, `solo-error`, `solo-imagepull`, `solo-pending`, `solo-oom`) — 7 healthy + 1 failing pod each
- Added `composite` scenario (default) — dynamically picks 2-3 random bad pods from the pool of 5, so every run is different
- Added `--scenario` / `-s` CLI flag to select mock data
- Added dedup/repetition guards to the ReAct loop to prevent infinite tool calls
- Removed `--describe` flag (agent decides when to dig deeper)

### Key learnings

- ReAct loops need repetition guards — LLMs will happily call `GET_PODS` twice and get the same data
- Mock data quality matters more than quantity: realistic log lines (timestamps, stack traces, error codes) make the agent's output far more convincing
- Composing scenarios from a healthy base + bad pod variants is cleaner than hardcoding each scenario

</details>
<details>
<summary><strong>2026-07-15</strong> — Repo tooling: uv, pre-commit, ruff</summary>

### What was done

- Switched from pip/requirements.txt to **uv** (pyproject.toml + uv.lock)
- Added pre-commit hooks: ruff lint/format + conventional commit enforcement
- Updated Makefile to use `uv run` — no manual venv activation needed
- Updated `.gitignore` and removed `requirements.txt`

</details>

---

## Projects

| #   | Project                                      | Status           | Description                    |
| --- | -------------------------------------------- | ---------------- | ------------------------------ |
| 01  | [K8s Health Monitor](01-k8s-health-monitor/) | ReAct agent + scenarios | Pod health summarization agent with iterative tool use |

---

## Setup

```bash
# First-time uv install:
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc    # reload PATH

# Then:
make install    # creates .venv + installs deps
source .venv/bin/activate
cp .env.example .env
# edit .env with your API key
make run        # or: python -m 01-k8s-health-monitor.src.cli
```

## Repo structure

```
├── 01-k8s-health-monitor/     # Project 1: K8s agent
│   ├── src/
│   │   ├── cli.py             # CLI entry point
│   │   ├── agent.py           # Agent logic (Model + Tools + Instructions)
│   │   └── k8s_client.py      # Pod collector with mock fallback
│   └── README.md              # Subproject docs + learning notes
├── shared/
│   └── llm.py                 # Shared LLM client (litellm)
├── questions.md               # Persistent Q&A learning diary
└── README.md                  # This file — build journal + index
```
