"""Shared LLM client using litellm for multi-provider support.

Supports: openai, anthropic, gemini, groq, ollama, openrouter, and 100+ more.
Swap providers by changing env vars — no code changes needed.
"""

import json
import os
import time
from dataclasses import dataclass, field

import litellm
from dotenv import load_dotenv

load_dotenv()

# Suppress litellm's noisy logging in production
litellm.suppress_debug_info = True


@dataclass
class LLMResponse:
    """Structured response from the LLM with metadata."""

    text: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    model: str
    raw: dict = field(default_factory=dict)


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
    """Send a chat completion request (backward-compatible).

    Returns just the text response string.
    """
    result = chat_raw(system_prompt, user_prompt, model, temperature, max_tokens)
    return result.text


def chat_raw(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> LLMResponse:
    """Send a chat completion request with full metadata.

    Returns an LLMResponse with text, latency, token counts, and raw response.
    """
    resolved_model = model or _resolve_model()

    start = time.perf_counter()
    response = litellm.completion(
        model=resolved_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    latency_ms = int((time.perf_counter() - start) * 1000)

    usage = response.usage or {}
    return LLMResponse(
        text=response.choices[0].message.content or "",
        latency_ms=latency_ms,
        tokens_in=getattr(usage, "prompt_tokens", 0),
        tokens_out=getattr(usage, "completion_tokens", 0),
        model=resolved_model,
        raw={"id": getattr(response, "id", ""), "finish_reason": response.choices[0].finish_reason},
    )


def chat_json(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> LLMResponse:
    """Send a chat completion requesting JSON output.

    Uses response_format for models that support it, falls back to
    prompt-level JSON instruction for models that don't.
    """
    resolved_model = model or _resolve_model()
    json_instruction = (
        "\n\nIMPORTANT: You MUST respond with valid JSON only. No markdown, no explanation outside the JSON."
    )
    json_system = system_prompt + json_instruction

    start = time.perf_counter()
    try:
        response = litellm.completion(
            model=resolved_model,
            messages=[
                {"role": "system", "content": json_system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = litellm.completion(
            model=resolved_model,
            messages=[
                {"role": "system", "content": json_system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    latency_ms = int((time.perf_counter() - start) * 1000)

    usage = response.usage or {}
    return LLMResponse(
        text=response.choices[0].message.content or "",
        latency_ms=latency_ms,
        tokens_in=getattr(usage, "prompt_tokens", 0),
        tokens_out=getattr(usage, "completion_tokens", 0),
        model=resolved_model,
        raw={"id": getattr(response, "id", ""), "finish_reason": response.choices[0].finish_reason},
    )


def extract_json(text: str) -> dict | None:
    """Extract a JSON object from text that might contain markdown fences or preamble."""
    text = text.strip()

    # Try direct parse first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    import re

    block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if block:
        try:
            obj = json.loads(block.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # Try finding the first { ... } in the text
    brace_start = text.find("{")
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[brace_start : i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
    return None
