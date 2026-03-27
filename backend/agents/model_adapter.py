"""
Model Adapter — model-agnostic LLM interface.

All agent code targets the `ModelAdapter` Protocol.
Concrete implementations are selected at startup via environment config.
"""
from __future__ import annotations

import os
from typing import AsyncIterator, Protocol, runtime_checkable

from openai import AsyncAzureOpenAI


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class ModelAdapter(Protocol):
    """Minimal async LLM interface consumed by agents."""

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> str:
        """Return the full completion as a string."""
        ...

    async def stream(
        self,
        system_prompt: str,
        user_message: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Yield token chunks for SSE streaming."""
        ...


# ── Azure OpenAI implementation ───────────────────────────────────────────────

class AzureOpenAIAdapter:
    """
    Wraps Azure OpenAI Async client.
    Deployment names are resolved from environment:
      AZURE_OPENAI_LISTENER_DEPLOYMENT   — fast cheap model (e.g. gpt-4o-mini)
      AZURE_OPENAI_AGENT_DEPLOYMENT      — reasoning model   (e.g. gpt-4o)
    """

    def __init__(self, deployment: str | None = None) -> None:
        self._client = AsyncAzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
        )
        self._deployment = deployment or os.environ.get(
            "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "chat4o"
        )

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    async def stream(
        self,
        system_prompt: str,
        user_message: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        async with await self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta


# ── Factory ───────────────────────────────────────────────────────────────────

def get_listener_adapter() -> AzureOpenAIAdapter:
    """Return adapter for the fast listener model (lower cost)."""
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "chat4o")
    return AzureOpenAIAdapter(deployment=deployment)


def get_agent_adapter() -> AzureOpenAIAdapter:
    """Return adapter for the reasoning agent model."""
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "chat4o")
    return AzureOpenAIAdapter(deployment=deployment)
