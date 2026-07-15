"""Kubernetes health monitoring agent with ReAct-style tool iteration.

The agent follows a loop:
  1. Collect initial pod data using get_pods()
  2. Send observations + available tools to the LLM
  3. LLM decides: either produce a final answer, or call a tool for more info
  4. If tool call: execute it, append result to conversation, go to step 2
  5. If final answer: return it
"""

import re

from shared.llm import chat

from .k8s_client import describe_pod, get_logs, get_pods

SYSTEM_PROMPT = """You are a Kubernetes cluster health monitoring assistant.
Your goal is to investigate pod health and produce a thorough, actionable summary.

You have access to these tools:
- GET_PODS: List all pods. Returns a table of name, namespace, status, restarts, ready, age.
- DESCRIBE_POD <pod_name> <namespace>: Get detailed pod description (events, conditions).
  Use this when a pod is in Pending, CrashLoopBackOff, ImagePullBackOff, or has restarts > 5.
- GET_LOGS <pod_name> <namespace>: Get the most recent log lines from a pod.
  Use this when a pod is in CrashLoopBackOff or Error state to find the root cause.

For each analysis, follow this investigation process:
1. ALWAYS start by calling GET_PODS to see the cluster state
2. For each unhealthy pod, decide which tool to use:
   - CrashLoopBackOff: GET_LOGS first, then DESCRIBE_POD for events
   - Pending: DESCRIBE_POD to check scheduling events
   - ImagePullBackOff: DESCRIBE_POD to see image pull errors
   - Restarts > 5 but Running: DESCRIBE_POD to check recent events
3. After gathering evidence, produce a final summary in this format:

FINAL ANSWER:

## Cluster Health
[1-2 sentence overview]

## Issues Found
### [pod name] — [namespace]
- **Status**: [status]
- **Root Cause**: [what you found from logs/describe]
- **Suggested Fix**: [specific actionable fix]
- **Evidence**: [key log line or event]

## Healthy Namespaces
[list]

## Overall Health Score: Healthy / Degraded / Critical

CRITICAL RULES:
- Call tools one at a time. Do NOT call multiple tools in parallel.
- Only report what you observe. Do NOT hallucinate log content or events.
- If a tool returns no useful data, say so.
- If all pods are healthy, say so and don't invent issues.
- You already ran GET_PODS and have the pod list. Do NOT call GET_PODS again.
- After gathering information from DESCRIBE_POD or GET_LOGS, produce FINAL ANSWER.
- Your output must begin with the tool name on its own line, or begin with "FINAL ANSWER:".
  Examples of correct tool calls:
  GET_LOGS payment-processor-b7c8d9e0f1-g5h6j payments
  DESCRIBE_POD cache-redis-2f4g6h8j0k-m3n4b cache
"""


def _mock_get_pods(namespace: str | None = None) -> str:
    pods = get_pods(namespace)
    if not pods:
        return "No pods found."

    header = f"{'NAMESPACE':<20} {'NAME':<50} {'STATUS':<20} {'RESTARTS':<10} {'READY':<8} {'AGE':<8}"
    sep = "-" * 116
    rows = []
    for p in pods:
        rows.append(f"{p.namespace:<20} {p.name:<50} {p.status:<20} {p.restarts:<10} {p.ready:<8} {p.age:<8}")
    return f"Pod listing:\n{header}\n{sep}\n" + "\n".join(rows)


def _mock_describe_pod(name: str, ns: str, **kwargs) -> str:
    return describe_pod(name, ns)


def _mock_get_logs(name: str, ns: str, **kwargs) -> str:
    return get_logs(name, ns)


_TOOL_PATTERNS = {
    r"^GET_PODS$": _mock_get_pods,
    r"^DESCRIBE_POD\s+(\S+)\s+(\S+)$": _mock_describe_pod,
    r"^GET_LOGS\s+(\S+)\s+(\S+)$": _mock_get_logs,
}


def _parse_tool_call(text: str, namespace: str | None) -> str | None:
    """Check if the LLM response contains a tool call. If so, execute it."""
    text = text.strip()

    for pattern, handler in _TOOL_PATTERNS.items():
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            return handler(*match.groups(), namespace=namespace)

    # Also check for the pattern inside a code block or after "Tool:" prefix
    for line in text.split("\n"):
        line = line.strip().strip("`").strip()
        for pattern, handler in _TOOL_PATTERNS.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return handler(*match.groups(), namespace=namespace)

    return None


def _generate_prompt(tool_result: str, conversation: list[str]) -> tuple[str, str]:
    """Generate the next prompt for the LLM based on conversation history.

    Returns (system_prompt, user_prompt).
    """
    history = "\n\n".join(conversation[-4:])  # last 4 turns for context

    user_prompt = f"""Here is the latest tool result:

{tool_result}

{history}

DECIDE: Either call another tool by writing its name on a single line, or write FINAL ANSWER and your summary.

Available tools:
- GET_PODS
- DESCRIBE_POD <pod_name> <namespace>
- GET_LOGS <pod_name> <namespace>"""

    return SYSTEM_PROMPT, user_prompt


def analyze(namespace: str | None = None) -> str:
    """Run the agent with ReAct-style tool iteration.

    The agent starts by listing pods, then iteratively investigates
    unhealthy pods by calling describe and logs tools.
    """
    conversation: list[str] = []
    max_iterations = 6
    # Start: get pods
    tool_result = _mock_get_pods(namespace)
    conversation.append(f"Tool result:\n{tool_result}")

    for i in range(max_iterations):
        system, user = _generate_prompt(tool_result, conversation)

        response = chat(
            system_prompt=system,
            user_prompt=user,
            temperature=0.2,
            max_tokens=1024,
        )

        # If the response contains "FINAL ANSWER" anywhere, stop
        if "FINAL ANSWER" in response.upper():
            return response

        # Parse tool call, but reject GET_PODS after the first iteration
        tool_output = _parse_tool_call(response, namespace)
        raw_call = response.strip().split("\n")[0].strip()
        is_get_pods = raw_call.upper().startswith("GET_PODS")

        if tool_output is None or is_get_pods:
            return response

        conversation.append(f"LLM decision:\n{response}")
        conversation.append(f"Tool result:\n{tool_output}")
        tool_result = tool_output

    return "Agent reached maximum iterations. Here's what was found:\n\n" + "\n\n".join(conversation)
