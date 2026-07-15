# K8s Health Monitor Agent

An AI agent that monitors a Kubernetes cluster and summarizes pod health in plain English.

## Table of Contents

- [How This Project Was Built](#how-this-project-was-built)
- [Learning Journal: Agent Design Foundations](#learning-journal-agent-design-foundations)
- [Learning Journal: Concepts Learned](#learning-journal-concepts-learned)
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

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up your LLM provider (copy and edit)
cp .env.example .env
# Edit .env with your API key

# Run the agent (uses mock data by default — no cluster needed)
python -m 01-k8s-health-monitor.src.cli
```

### Using a real cluster

1. Install [Kind](https://kind.sigs.k8s.io/) or start a cluster
2. Ensure `kubectl` is configured:
   ```bash
   kubectl cluster-info
   ```
3. Run the agent — it auto-detects the cluster

---

## Usage

```bash
# Basic health check (all namespaces)
python -m 01-k8s-health-monitor.src.cli

# Filter by namespace
python -m 01-k8s-health-monitor.src.cli --namespace default

# Include detailed pod descriptions for unhealthy pods
python -m 01-k8s-health-monitor.src.cli --describe

# Watch mode — re-analyze every 30 seconds
python -m 01-k8s-health-monitor.src.cli --watch

# Or install and use directly:
pip install -e .
k8s-health
k8s-health --namespace default --describe
```

---

## Project Structure

```
01-k8s-health-monitor/
├── src/
│   ├── __init__.py
│   ├── cli.py         # CLI entry point (typer)
│   ├── agent.py       # Agent logic (Model + Tools + Instructions)
│   └── k8s_client.py  # K8s data collection (kubectl + mock fallback)
├── tests/
└── README.md
```

---

## Configuration

See `.env.example` for all config options:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `gemini` | Which provider to use |
| `AGENT_MODEL` | `gemini/gemini-2.0-flash-exp` | Full model identifier for litellm |
| `GEMINI_API_KEY` | — | Your Gemini API key |
| `OPENAI_API_KEY` | — | Your OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Your Anthropic API key |
| `GROQ_API_KEY` | — | Your Groq API key |

---

## Roadmap

- [ ] Support `--output json` for machine-readable output
- [ ] Add Slack/email notifications for unhealthy pods
- [ ] Add historical analysis — track health over time
- [ ] Support filtering by label selectors
- [ ] Deploy as a Kubernetes CronJob that posts to a channel
- [ ] Add alert thresholds (e.g. "if restarts > 5, flag as critical")
