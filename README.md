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

### Why this matters

This established the foundation: without scaffolding and a CLI, there's no way to interact with the agent. Choosing litellm from day one meant zero lock-in — the agent can switch from Gemini (free dev) to Claude (production) by changing one env var. Using `subprocess` + `kubectl` over the K8s SDK kept dependencies minimal and behavior transparent.

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

### Why this matters

A one-shot LLM call can only analyse data you give it. The ReAct loop transforms the agent from a passive summariser into an active investigator — it decides which pods to dig into, calls `GET_LOGS` and `DESCRIBE_POD` on its own, and iterates until it has enough evidence. This mirrors how a human SRE would troubleshoot: glance at the dashboard, then drill into the failing pods. The repetition guards prevent infinite loops (a common failure mode for agents).

</details>
<details>
<summary><strong>2026-07-14</strong> — Repo tooling: uv, pre-commit, ruff</summary>

### What was done

- Switched from pip/requirements.txt to **uv** (pyproject.toml + uv.lock)
- Added pre-commit hooks: ruff lint/format + conventional commit enforcement
- Updated Makefile to use `uv run` — no manual venv activation needed
- Updated `.gitignore` and removed `requirements.txt`

### Why this matters

uv is dramatically faster than pip (no dependency resolution on every install) and locks dependencies deterministically. Pre-commit hooks catch formatting issues and enforce conventional commits before code ever lands — this keeps the git history clean and reviewable. Ruff replaces both flake8 + isort + black with a single tool that runs in milliseconds.

</details>
<details>
<summary><strong>2026-07-14</strong> — Alert thresholds: deterministic pod severity scoring</summary>

### What was done

- Created `alerts.py` — pure-function severity module independent of the LLM
  - `score_pod()` — maps a `PodInfo` to `"critical"`, `"warning"`, or `"healthy"` using status checks, restart thresholds (≥5 critical, ≥3 warning), and ready-container ratios (0 critical, partial warning)
  - `sorted_pods()` — orders pods by descending severity
  - `severity_counts()` — returns a dict tally of each severity level
  - `severity_stats()` — one-line human-readable summary (e.g. "2 critical, 1 warning, 6 healthy")
- Wired alerts into `agent.py` via `analyze_with_alerts()` — runs the ReAct loop then appends a deterministic alert summary below the LLM response
- Wired alerts into `cli.py` — output now includes LLM analysis + severity block
- Deleted duplicate/broken draft `alerts.py` from `ai_agent_build/`
- Fixed pluralization bug ("healthys" → "healthy") in severity output

### Key learnings

- Deterministic scoring provides a reliable safety net beneath the LLM — if the model hallucinates, the threshold block is still correct
- Post-hoc appendix pattern (run LLM first, append alerts after) keeps the agent prompt unchanged and is trivial to wire in
- Pluralization edge cases matter for UX: "healthy" is uncountable ("6 healthy" not "6 healthys")

### Why this matters

LLMs are not deterministic — the same pod data can produce different summaries on different runs. The alert threshold module provides a **deterministic safety net**: no matter what the LLM says, the severity block underneath is computed from hard rules. If the LLM hallucinates a healthy pod as critical or misses an ImagePullBackOff, the alerts don't lie. This is the "belt and suspenders" approach to AI reliability.

</details>

---

## Projects

| #   | Project                                      | Status           | Description                    |
| --- | -------------------------------------------- | ---------------- | ------------------------------ |
| 01  | [K8s Health Monitor](01-k8s-health-monitor/) | Alert thresholds wired | Pod health summarization agent with ReAct loop + deterministic alert scoring |

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
│   │   ├── alerts.py          # Deterministic pod severity scoring (LLM-independent)
│   │   └── k8s_client.py      # Pod collector with mock fallback
│   └── README.md              # Subproject docs + learning notes
├── shared/
│   └── llm.py                 # Shared LLM client (litellm)
├── questions.md               # Persistent Q&A learning diary
└── README.md                  # This file — build journal + index

---

## Next steps

### Human-readable cluster health report

Yes — this is basically a richer version of the alert threshold block. Instead of just listing pods by severity, the agent could output a structured report with:
- **Executive summary**: "7/10 pods healthy. Cluster is degraded."
- **Top 3 issues** ranked by impact
- **Timeline**: when each pod entered its current state
- **Trend**: "3 warnings, up from 1 yesterday"
- **Suggested actions**: priority-ordered fixes

This is already partially done: the LLM produces the narrative, alerts produce the deterministic score. The next step is merging them into a single formatted report (Markdown or plaintext) that could be saved to a file or emailed.

### Publishing to a website

Also possible. Options from simplest to most sophisticated:

1. **Static HTML export** — `--report report.html` flag on the CLI that wraps the markdown output in a minimal HTML template. Zero infra, just a file on disk. Could serve via `python -m http.server` or GitHub Pages.

2. **FastAPI dashboard** — a lightweight web server (`pip install fastapi uvicorn`) that runs the analysis on each request and renders the result. Useful for on-demand checks.

3. **Scheduled updates** — use a cron job or GitHub Actions workflow to run the agent every N minutes and publish the report to a static site (GitHub Pages, S3, Netlify). The most "set and forget" option.

4. **An actual dashboard** — embed the alert severity counts into a real dashboard (Grafana, Datadog, etc.) via their APIs. Overkill for this project but would be the production-grade solution.

The static export + GitHub Actions route is probably the sweet spot: minimal code, zero hosting cost, and the report gets version-controlled alongside the code.
```
