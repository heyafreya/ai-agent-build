"""Kubernetes health monitoring agent with ReAct-style tool iteration.

The agent follows a loop:
  1. Collect initial pod data using get_pods()
  2. Send observations + available tools to the LLM (structured JSON output)
  3. LLM decides: either produce a final answer, or call a tool for more info
  4. If tool call: execute it, append result to conversation, go to step 2
  5. If final answer: return it

Every step is captured in a TraceStep for debugging, evaluation, and comparison.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from shared.llm import LLMResponse, chat_json, extract_json

from .alerts import score_pod, severity_counts
from .k8s_client import describe_pod, get_logs, get_pods

# ── System prompt ──────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Kubernetes cluster health monitoring assistant.
Your goal is to investigate pod health and produce a thorough, actionable summary.

You have access to these tools:
- GET_PODS: List all pods. Returns a table of name, namespace, status, restarts, ready, age.
- DESCRIBE_POD: Get detailed pod description (events, conditions). Requires pod_name and namespace.
- GET_LOGS: Get the most recent log lines from a pod. Requires pod_name and namespace.

RESPONSE FORMAT:
You MUST respond with a single JSON object. No markdown, no explanation outside the JSON.

To call a tool:
{"action": "GET_PODS"}
{"action": "DESCRIBE_POD", "pod_name": "payment-processor-xyz", "namespace": "payments"}
{"action": "GET_LOGS", "pod_name": "payment-processor-xyz", "namespace": "payments"}

To produce your final answer:
{"action": "FINAL_ANSWER", "summary": "## Cluster Health\\n...your full markdown summary here..."}

INVESTIGATION PROCESS:
1. Start by calling GET_PODS to see the cluster state (skip this in FOCUS MODE).
2. For each unhealthy pod, investigate:
   - CrashLoopBackOff: GET_LOGS first, then DESCRIBE_POD for events
   - Pending: DESCRIBE_POD to check scheduling events
   - ImagePullBackOff: DESCRIBE_POD to see image pull errors
   - OOMKilled: GET_LOGS for memory errors, then DESCRIBE_POD
   - Restarts > 5 but Running: DESCRIBE_POD to check recent events
3. After gathering evidence, produce FINAL_ANSWER with your summary.

SUMMARY FORMAT (inside the "summary" field):
## Cluster Health
[1-2 sentence overview]

## Issues Found
### [pod name] — [namespace]
- **Status**: [status]
- **Root Cause**: [what you found from logs/describe]
- **Suggested Fix**: [specific actionable fix]
- **Evidence**: [key log line or event]

## Overall Health Score: Healthy / Degraded / Critical

RULES:
- Call tools one at a time. Do NOT call multiple tools in parallel.
- Only report what you observe. Do NOT hallucinate log content or events.
- If a tool returns no useful data, say so.
- If all pods are healthy, say so and don't invent issues.
- Do NOT call GET_PODS again after the first iteration.
- After gathering information from DESCRIBE_POD or GET_LOGS, produce FINAL_ANSWER.
- You may only reference pods that appear in the GET_PODS listing.
- Health score rules:
  - "Healthy" if ALL pods are Running with restarts < 3 and full ready ratios.
  - "Degraded" if at least one pod has restarts >= 3 or a partial ready ratio.
  - "Critical" if any pod is in CrashLoopBackOff, Error, ImagePullBackOff, or OOMKilled.
"""

FOLLOW_UP_SYSTEM_PROMPT = """You are a Kubernetes health assistant continuing a conversation about pod health.
You have access to the same tools as before:
- GET_PODS: List all pods.
- DESCRIBE_POD: Get detailed pod description. Requires pod_name and namespace.
- GET_LOGS: Get recent log lines. Requires pod_name and namespace.

RESPONSE FORMAT — single JSON object:
To call a tool:
{"action": "GET_PODS"}
{"action": "DESCRIBE_POD", "pod_name": "...", "namespace": "..."}
{"action": "GET_LOGS", "pod_name": "...", "namespace": "..."}

To answer the user's question:
{"action": "FINAL_ANSWER", "summary": "your markdown response here..."}

RULES:
- You may call tools to investigate further before answering.
- Only report what you observe. Do NOT hallucinate.
- Keep your response focused on the user's question.
- You may only reference pods from the original analysis.
"""

# ── Trace data model ───────────────────────────────────────────────


class TraceStep(BaseModel):
    """One iteration of the ReAct loop."""

    iteration: int
    action: str  # tool name or FINAL_ANSWER
    tool_input: dict | None = None
    tool_output: str | None = None
    llm_raw: str = ""  # raw JSON from LLM
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    error: str | None = None


class AgentTrace(BaseModel):
    """Full trace of an agent run."""

    conversation_id: str = ""
    scenario: str = "composite"
    focus_pod: str | None = None
    steps: list[TraceStep] = []
    final_answer: str = ""
    total_latency_ms: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    model: str = ""
    iterations: int = 0


# ── Tool execution ─────────────────────────────────────────────────


def _exec_get_pods(namespace: str | None = None) -> str:
    pods = get_pods(namespace)
    if not pods:
        return "No pods found."
    header = f"{'NAMESPACE':<20} {'NAME':<50} {'STATUS':<20} {'RESTARTS':<10} {'READY':<8} {'AGE':<8}"
    sep = "-" * 116
    rows = [f"{p.namespace:<20} {p.name:<50} {p.status:<20} {p.restarts:<10} {p.ready:<8} {p.age:<8}" for p in pods]
    return f"Pod listing:\n{header}\n{sep}\n" + "\n".join(rows)


def _exec_describe_pod(name: str, namespace: str) -> str:
    return describe_pod(name, namespace)


def _exec_get_logs(name: str, namespace: str) -> str:
    return get_logs(name, namespace)


def _execute_tool(action: dict, namespace: str | None) -> str:
    """Execute a tool given a parsed action dict. Returns tool output string."""
    tool = action.get("action", "").upper()
    if tool == "GET_PODS":
        return _exec_get_pods(namespace)
    elif tool == "DESCRIBE_POD":
        return _exec_describe_pod(action["pod_name"], action.get("namespace", namespace or "default"))
    elif tool == "GET_LOGS":
        return _exec_get_logs(action["pod_name"], action.get("namespace", namespace or "default"))
    else:
        return f"Unknown tool: {tool}"


def _is_tool_call(action: dict) -> bool:
    return action.get("action", "").upper() in ("GET_PODS", "DESCRIBE_POD", "GET_LOGS")


# ── Prompt generation ──────────────────────────────────────────────


def _build_initial_system(pods, focus_pod: str | None = None) -> str:
    pod_names = [p.name for p in pods]
    pod_list = "\n".join(f"- {n}" for n in pod_names)
    system = SYSTEM_PROMPT + f"\n\nEXISTING PODS (you may only reference these):\n{pod_list}"
    if focus_pod:
        system += (
            f"\n\nFOCUS MODE: You are investigating a SINGLE pod: '{focus_pod}'. "
            "Do NOT call GET_PODS. Start by calling DESCRIBE_POD or GET_LOGS on this pod. "
            "Report ONLY on this pod. Do not mention other pods."
        )
    return system


def _build_user_prompt(tool_result: str, conversation: list[str]) -> str:
    history = "\n\n".join(conversation[-6:])
    return f"""Here is the latest tool result:

{tool_result}

{history}

DECIDE: Respond with a JSON object. Either call another tool or produce FINAL_ANSWER."""


# ── Core agent loop ────────────────────────────────────────────────


def analyze(
    namespace: str | None = None,
    focus_pod: str | None = None,
    model: str | None = None,
    scenario: str = "composite",
) -> tuple[str, AgentTrace]:
    """Run the agent with ReAct-style tool iteration.

    Returns (final_answer_text, trace).
    """
    trace = AgentTrace(
        conversation_id=uuid.uuid4().hex[:12],
        scenario=scenario,
        focus_pod=focus_pod,
        model=model or "",
    )
    conversation: list[str] = []
    max_iterations = 8
    pods = get_pods(namespace)
    system = _build_initial_system(pods, focus_pod)

    # Initial tool call
    if focus_pod:
        focus_ns = namespace
        for p in pods:
            if p.name == focus_pod:
                focus_ns = p.namespace
                break
        tool_result = _exec_describe_pod(focus_pod, focus_ns or "default")
        conversation.append(f"Tool result (describe {focus_pod}):\n{tool_result}")
        initial_step = TraceStep(
            iteration=0,
            action="DESCRIBE_POD",
            tool_input={"pod_name": focus_pod, "namespace": focus_ns or "default"},
            tool_output=tool_result,
        )
    else:
        tool_result = _exec_get_pods(namespace)
        conversation.append(f"Tool result:\n{tool_result}")
        initial_step = TraceStep(
            iteration=0,
            action="GET_PODS",
            tool_input={"namespace": namespace},
            tool_output=tool_result,
        )
    trace.steps.append(initial_step)

    for i in range(1, max_iterations + 1):
        user_prompt = _build_user_prompt(tool_result, conversation)

        llm_resp: LLMResponse = chat_json(
            system_prompt=system,
            user_prompt=user_prompt,
            model=model,
            temperature=0.2,
            max_tokens=1536,
        )

        # Parse JSON response
        parsed = extract_json(llm_resp.text)
        step = TraceStep(
            iteration=i,
            action="PARSE_ERROR",
            llm_raw=llm_resp.text,
            latency_ms=llm_resp.latency_ms,
            tokens_in=llm_resp.tokens_in,
            tokens_out=llm_resp.tokens_out,
            model=llm_resp.model,
        )
        trace.total_latency_ms += llm_resp.latency_ms
        trace.total_tokens_in += llm_resp.tokens_in
        trace.total_tokens_out += llm_resp.tokens_out
        trace.model = llm_resp.model

        if parsed is None:
            # Fallback: try to detect FINAL ANSWER in raw text
            if "FINAL ANSWER" in llm_resp.text.upper() or "FINAL_ANSWER" in llm_resp.text.upper():
                step.action = "FINAL_ANSWER"
                # Extract everything after FINAL ANSWER
                import re

                match = re.search(r"FINAL[_ ]ANSWER[:\s]*(.*)", llm_resp.text, re.IGNORECASE | re.DOTALL)
                step.tool_output = match.group(1).strip() if match else llm_resp.text
                trace.steps.append(step)
                trace.final_answer = step.tool_output
                trace.iterations = i
                return trace.final_answer, trace
            step.error = "Failed to parse LLM response as JSON"
            trace.steps.append(step)
            trace.final_answer = llm_resp.text
            trace.iterations = i
            return llm_resp.text, trace

        action_name = parsed.get("action", "").upper()
        step.action = action_name
        step.tool_input = {k: v for k, v in parsed.items() if k != "action"}
        step.llm_raw = llm_resp.text

        if action_name == "FINAL_ANSWER":
            step.tool_output = parsed.get("summary", "")
            trace.steps.append(step)
            trace.final_answer = step.tool_output
            trace.iterations = i
            return trace.final_answer, trace

        if _is_tool_call(parsed):
            # Reject GET_PODS after first iteration
            if action_name == "GET_PODS" and i > 1:
                step.error = "GET_PODS rejected after first iteration"
                trace.steps.append(step)
                trace.final_answer = llm_resp.text
                trace.iterations = i
                return llm_resp.text, trace

            tool_output = _execute_tool(parsed, namespace)
            step.tool_output = tool_output
            trace.steps.append(step)

            conversation.append(f"LLM decision: {action_name}\nTool result:\n{tool_output}")
            tool_result = tool_output
        else:
            step.error = f"Unknown action: {action_name}"
            trace.steps.append(step)
            trace.final_answer = llm_resp.text
            trace.iterations = i
            return llm_resp.text, trace

    # Max iterations reached
    trace.iterations = max_iterations
    fallback = "Agent reached maximum iterations. Here's what was found:\n\n" + "\n\n".join(conversation)
    trace.final_answer = fallback
    return fallback, trace


# ── Follow-up chat ─────────────────────────────────────────────────


def chat_follow_up(
    message: str,
    conversation_history: list[dict],
    conversation_id: str,
    model: str | None = None,
) -> tuple[str, list[dict]]:
    """Continue a conversation about pod health.

    conversation_history is a list of {"role": "user"|"assistant", "content": str}.
    Returns (response_text, updated_history).
    """
    updated = conversation_history + [{"role": "user", "content": message}]
    messages_text = "\n".join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in updated)

    user_prompt = f"""Previous conversation:\n{messages_text}

Respond to the user's latest message. You may call tools to investigate further.
Remember: respond with a single JSON object."""

    llm_resp = chat_json(
        system_prompt=FOLLOW_UP_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=model,
        temperature=0.3,
        max_tokens=1536,
    )

    parsed = extract_json(llm_resp.text)
    if parsed and parsed.get("action") == "FINAL_ANSWER":
        response_text = parsed.get("summary", llm_resp.text)
    elif parsed and _is_tool_call(parsed):
        tool_output = _execute_tool(parsed, None)
        response_text = f"Based on further investigation:\n\n```\n{tool_output}\n```"
    else:
        response_text = llm_resp.text

    updated.append({"role": "assistant", "content": response_text})
    return response_text, updated


# ── analyze_with_alerts (backward-compatible wrapper) ──────────────


def analyze_with_alerts(
    namespace: str | None = None,
    focus_pod: str | None = None,
    model: str | None = None,
    scenario: str = "composite",
) -> str:
    """Run the agent and append deterministic alert severity summary.

    Backward-compatible: returns just the text.
    """
    pods = get_pods(namespace)
    llm_result, _trace = analyze(namespace, focus_pod=focus_pod, model=model, scenario=scenario)

    if focus_pod:
        pods = [p for p in pods if p.name == focus_pod]

    counts = severity_counts(pods)
    order = ["critical", "warning", "healthy"]
    severity_parts = []
    for s in order:
        n = counts[s]
        if n > 0:
            label = f"{n} {s}"
            if s != "healthy" and n > 1:
                label += "s"
            severity_parts.append(label)
    severity_str = ", ".join(severity_parts) if severity_parts else "No pods"
    block = f"\n\n--- Alert Thresholds ---\nSeverity: {severity_str}\n\n"
    for s in order:
        pds = [p for p in pods if score_pod(p) == s]
        if pds:
            block += f"{s.upper()}:\n"
            for p in pds:
                block += f"- {p.name} ({p.namespace}): {p.status} - restarts: {p.restarts}, ready: {p.ready}\n"
            block += "\n"
    return llm_result + block
