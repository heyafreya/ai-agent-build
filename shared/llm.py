"""Shared LLM client using litellm for multi-provider support.

Supports: openai, anthropic, gemini, groq, ollama, openrouter, and 100+ more.
Swap providers by changing env vars — no code changes needed.
"""

import os

import litellm
from dotenv import load_dotenv

load_dotenv()


def get_client():
    """Returns a litellm-compatible config.

    litellm is a unified interface — you call litellm.completion()
    directly with model="provider/model-name".
    No separate client object needed.
    """
    return litellm


def _resolve_model() -> str:
    return os.getenv("AGENT_MODEL", "gemini/gemini-2.0-flash-exp")


def chat(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """Send a chat completion request to the configured LLM provider.

    Args:
        system_prompt: System-level instructions for the agent.
        user_prompt: The user's query / data to analyze.
        model: Override the default model (e.g. "groq/llama3-70b-8192").
        temperature: Lower = more deterministic outputs.
        max_tokens: Maximum response length.

    Returns:
        The LLM's text response.
    """
    resolved_model = model or _resolve_model()

    response = litellm.completion(
        model=resolved_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return response.choices[0].message.content
