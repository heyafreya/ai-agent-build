"""Kubernetes health monitoring agent.

This is the core agent logic — the "Model + Tools + Instructions" pattern:
  - Model:   litellm-compatible LLM (Gemini, Claude, GPT, etc.)
  - Tools:   k8s_client.get_pods(), k8s_client.describe_pod()
  - Instructions: The system prompt defining agent behavior.

The agent collects pod data, formats it, and asks the LLM to produce
a plain-English health summary with actionable recommendations.
"""

from typing import Optional

from shared.llm import chat

from .k8s_client import get_pods, describe_pod


SYSTEM_PROMPT = """You are a Kubernetes cluster health monitoring assistant.
Your role is to analyze pod data and produce clear, plain-English summaries.

For each analysis, you MUST:
1. Summarize the overall cluster health in 1-2 sentences
2. List any unhealthy or problematic pods with:
   - What's wrong (status, restarts, readiness)
   - The likely cause (use your knowledge of K8s)
   - Recommended action
3. Highlight the healthiest namespaces
4. Give an overall health score: Healthy / Degraded / Critical

Be concise. Use technical terms only when necessary, and explain them.
Never hallucinate pod details — only report what's in the data provided.

CRITICAL RULES:
- If ALL pods are healthy, say so and don't make up issues
- If data is empty, report that the namespace has no pods
- Do NOT invent pod statuses or conditions
"""


def _format_pod_table(pods) -> str:
    """Format pod list into a readable table for the LLM."""
    lines = [
        f"{'NAMESPACE':<20} {'NAME':<50} {'STATUS':<20} {'RESTARTS':<10} {'READY':<8} {'AGE':<8} {'NODE':<20}"
    ]
    lines.append("-" * 136)
    for p in pods:
        lines.append(
            f"{p.namespace:<20} {p.name:<50} {p.status:<20} {p.restarts:<10} {p.ready:<8} {p.age:<8} {p.node:<20}"
        )
    return "\n".join(lines)


def analyze(namespace: Optional[str] = None, describe: bool = False) -> str:
    """Run the health analysis agent end-to-end.

    Steps:
        1. Collect pod data from cluster (or mock)
        2. Optionally fetch detailed descriptions for unhealthy pods
        3. Send formatted data to LLM
        4. Return plain-English summary

    Args:
        namespace: Filter to a specific namespace (None = all).
        describe: If True, include full describe output for unhealthy pods.

    Returns:
        The LLM's health summary.
    """
    pods = get_pods(namespace)

    if not pods:
        ns = f"namespace '{namespace}'" if namespace else "the cluster"
        return f"No pods found in {ns}."

    formatted = _format_pod_table(pods)

    details = ""
    if describe:
        unhealthy = [p for p in pods if p.status not in ("Running", "Completed")]
        for pod in unhealthy:
            details += f"\n\n=== describe pod {pod.name} ===\n"
            details += describe_pod(pod.name, pod.namespace)

    user_prompt = f"""Here is the current pod status data:

{formatted}
{details}

Please analyze the health of this cluster and provide a plain-English summary."""

    return chat(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
    )
