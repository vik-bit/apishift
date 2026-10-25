"""One small interface over the LLM providers: complete(system, user) -> text.

Plain English: the fixer only needs "here is a prompt, give me text back". Hiding each provider's
API behind that keeps the fixer identical for Groq and Claude, and lets tests use a scripted fake.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from ..config import Settings


class LLMError(RuntimeError):
    """A provider failure, with a message a person can act on."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class Provider(Protocol):
    name: str
    model: str
    usage: Usage

    def complete(self, system: str, user: str) -> str: ...


class GroqProvider:
    name = "groq"

    def __init__(self, model: str, effort: str = "medium", client=None):
        import groq

        self._groq = groq
        self.model = model
        self.effort = effort
        self.usage = Usage()
        # Groq's free tier limits tokens per minute; the SDK waits for retry-after between attempts.
        self.client = client or groq.Groq(max_retries=5, timeout=180)

    def complete(self, system: str, user: str) -> str:
        groq = self._groq
        kwargs = dict(model=self.model, temperature=0.1, max_completion_tokens=8192,
                      messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        if self.model.startswith("openai/gpt-oss") and self.effort in ("low", "medium", "high"):
            kwargs["reasoning_effort"] = self.effort
        for attempt in range(3):
            try:
                r = self.client.chat.completions.create(**kwargs)
                break
            except groq.BadRequestError as exc:
                # Groq occasionally rejects a generation it can't parse; asking again usually works.
                if "output_parse_failed" in str(exc) and attempt < 2:
                    continue
                raise LLMError(f"Groq rejected the request: {exc}") from exc
            except groq.AuthenticationError as exc:
                raise LLMError("The Groq API key was rejected. Check GROQ_API_KEY.") from exc
            except groq.RateLimitError as exc:
                raise LLMError("Groq is rate-limiting this key; wait a minute and retry.") from exc
            except groq.APIConnectionError as exc:
                raise LLMError("Couldn't reach Groq. Check the internet connection.") from exc
        self.usage.calls += 1
        if r.usage:
            self.usage.input_tokens += r.usage.prompt_tokens or 0
            self.usage.output_tokens += r.usage.completion_tokens or 0
        return r.choices[0].message.content or ""


class ClaudeProvider:
    name = "claude"
    _FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}

    def __init__(self, model: str, effort: str = "medium", client=None):
        import anthropic

        self._anthropic = anthropic
        self.model = model
        self.effort = effort
        self.usage = Usage()
        workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
        self.client = client or anthropic.Anthropic(
            default_headers={"anthropic-workspace-id": workspace} if workspace else None)

    def complete(self, system: str, user: str) -> str:
        a = self._anthropic
        kwargs = dict(model=self.model, max_tokens=16000, system=system,
                      messages=[{"role": "user", "content": user}])
        if self.effort != "none":
            kwargs["output_config"] = {"effort": self.effort}
        try:
            if self.model in self._FALLBACK_MODELS:
                r = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
            else:
                r = self.client.messages.create(**kwargs)
        except a.AuthenticationError as exc:
            raise LLMError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from exc
        except a.RateLimitError as exc:
            raise LLMError("Anthropic is rate-limiting this key; wait a minute and retry.") from exc
        except a.BadRequestError as exc:
            if "credit" in str(exc).lower():
                raise LLMError("The Anthropic account has no remaining credit.") from exc
            raise LLMError(f"Anthropic rejected the request: {exc}") from exc
        except a.APIConnectionError as exc:
            raise LLMError("Couldn't reach Anthropic. Check the internet connection.") from exc
        if r.stop_reason == "refusal":
            raise LLMError("The model declined this request.")
        self.usage.calls += 1
        self.usage.input_tokens += r.usage.input_tokens
        self.usage.output_tokens += r.usage.output_tokens
        return "".join(b.text for b in r.content if b.type == "text")


@dataclass
class ScriptedProvider:
    """For tests: returns canned replies in order and records every prompt."""

    replies: list[str]
    name: str = "scripted"
    model: str = "scripted"
    usage: Usage = field(default_factory=Usage)
    prompts: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        self.usage.calls += 1
        if not self.replies:
            raise LLMError("ScriptedProvider ran out of replies")
        return self.replies.pop(0)


def make_provider(settings: Settings) -> Provider | None:
    p = settings.resolved_provider
    if p == "groq":
        return GroqProvider(settings.groq_model, settings.effort)
    if p == "claude":
        return ClaudeProvider(settings.claude_model, settings.effort)
    return None
