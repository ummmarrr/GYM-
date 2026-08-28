"""Text generation, spread across more than one provider.

Every free tier runs out. Rather than apologising to the member when Gemini's daily quota is
gone, the chain moves to the next provider and keeps answering. A provider that reports
exhaustion is skipped for a cooldown period so the next caller does not pay its timeout again.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4

NOT_CONFIGURED = (
    "The AI coach is not configured yet. Add GEMINI_API_KEY or GROQ_API_KEY to your .env file, "
    "then restart the backend."
)
ALL_PROVIDERS_DOWN = (
    "I could not reach the coaching model just now. Please try again in a moment, or ask "
    "reception for help."
)


@dataclass(frozen=True)
class ToolSpec:
    """A function the model may call. ``parameters`` is a JSON Schema object."""

    name: str
    description: str
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict
    id: str = ""


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str = "none"
    tool_calls: tuple[ToolCall, ...] = ()


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot answer, so the chain can try the next one.

    ``exhausted`` marks a quota or rate-limit refusal, which is worth remembering: the same
    provider will refuse every other caller too until its window resets.
    """

    def __init__(self, message: str, *, exhausted: bool = False) -> None:
        super().__init__(message)
        self.exhausted = exhausted


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.gemini_model
        self.max_output_tokens = settings.llm_max_output_tokens
        self._client = None
        if settings.gemini_api_key:
            from google import genai

            self._client = genai.Client(
                api_key=settings.gemini_api_key,
                # Without a deadline the SDK retries a rate-limited call for minutes and the
                # chat window just spins. Fail fast so the chain can move on.
                http_options={
                    "timeout": settings.llm_timeout_seconds * 1000,
                    "retry_options": {"attempts": settings.llm_retry_attempts},
                },
            )

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    @staticmethod
    def _is_rate_limited(error: Exception) -> bool:
        return getattr(error, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(error)

    def generate(self, system_instruction: str, prompt: str) -> LLMResult:
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "system_instruction": system_instruction,
                    "temperature": 0.3,
                    "max_output_tokens": self.max_output_tokens,
                },
            )
        except Exception as caught:
            raise ProviderUnavailable(
                str(caught), exhausted=self._is_rate_limited(caught)
            ) from caught

        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            logger.info(
                "gemini usage: prompt=%s output=%s total=%s",
                getattr(usage, "prompt_token_count", "?"),
                getattr(usage, "candidates_token_count", "?"),
                getattr(usage, "total_token_count", "?"),
            )
        if not response.text:
            raise ProviderUnavailable("gemini returned an empty response")
        return LLMResult(response.text, provider=self.name)

    def generate_with_tools(
        self,
        system_instruction: str,
        prompt: str,
        tools: Sequence[ToolSpec],
        execute: Callable[[str, dict], str],
        max_rounds: int = MAX_TOOL_ROUNDS,
    ) -> LLMResult:
        from google.genai import types

        declarations = [
            types.FunctionDeclaration(
                name=spec.name,
                description=spec.description,
                parameters=spec.parameters,
            )
            for spec in tools
        ]
        contents: list = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        last_text = ""

        for _ in range(max_rounds):
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config={
                        "system_instruction": system_instruction,
                        "temperature": 0.3,
                        "max_output_tokens": self.max_output_tokens,
                        "tools": [{"function_declarations": declarations}],
                    },
                )
            except Exception as caught:
                raise ProviderUnavailable(
                    str(caught), exhausted=self._is_rate_limited(caught)
                ) from caught

            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                logger.info(
                    "gemini usage: prompt=%s output=%s total=%s",
                    getattr(usage, "prompt_token_count", "?"),
                    getattr(usage, "candidates_token_count", "?"),
                    getattr(usage, "total_token_count", "?"),
                )

            calls = _gemini_tool_calls(response)
            try:
                text = (response.text or "").strip()
            except Exception:
                text = ""
            if text:
                last_text = text
            if not calls:
                if not last_text:
                    raise ProviderUnavailable("gemini returned an empty response")
                return LLMResult(last_text, provider=self.name)

            model_content = response.candidates[0].content
            contents.append(model_content)
            response_parts = []
            for call in calls:
                logger.info("FitBot tool: %s(%s)", call.name, call.arguments)
                output = execute(call.name, call.arguments)
                response_parts.append(
                    types.Part.from_function_response(
                        name=call.name, response={"result": output}
                    )
                )
            contents.append(types.Content(role="user", parts=response_parts))

        return LLMResult(
            last_text or "I looked that up but could not finish the reply.",
            provider=self.name,
        )


class GroqProvider:
    """Groq over its OpenAI-compatible endpoint.

    Plain HTTP rather than the vendor SDK: the request is a single JSON POST, and httpx is
    already a dependency.
    """

    name = "groq"

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.groq_api_key
        self.model = settings.groq_model
        self.base_url = settings.groq_base_url.rstrip("/")
        self.timeout = settings.llm_timeout_seconds
        self.max_output_tokens = settings.llm_max_output_tokens

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, system_instruction: str, prompt: str) -> LLMResult:
        import httpx

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": self.max_output_tokens,
                },
                timeout=self.timeout,
            )
        except Exception as caught:
            raise ProviderUnavailable(str(caught)) from caught

        if response.status_code == 429:
            raise ProviderUnavailable("groq rate limited", exhausted=True)
        if response.status_code >= 400:
            raise ProviderUnavailable(f"groq returned {response.status_code}")

        payload = response.json()
        usage = payload.get("usage") or {}
        logger.info(
            "groq usage: prompt=%s output=%s total=%s",
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            usage.get("total_tokens", "?"),
        )
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as caught:
            raise ProviderUnavailable("groq returned an unreadable response") from caught
        if not text:
            raise ProviderUnavailable("groq returned an empty response")
        return LLMResult(text, provider=self.name)

    def generate_with_tools(
        self,
        system_instruction: str,
        prompt: str,
        tools: Sequence[ToolSpec],
        execute: Callable[[str, dict], str],
        max_rounds: int = MAX_TOOL_ROUNDS,
    ) -> LLMResult:
        import httpx

        messages: list[dict] = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]
        payload_tools = [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in tools
        ]
        last_text = ""

        for _ in range(max_rounds):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": messages,
                        "tools": payload_tools,
                        "temperature": 0.3,
                        "max_tokens": self.max_output_tokens,
                    },
                    timeout=self.timeout,
                )
            except Exception as caught:
                raise ProviderUnavailable(str(caught)) from caught

            if response.status_code == 429:
                raise ProviderUnavailable("groq rate limited", exhausted=True)
            if response.status_code >= 400:
                raise ProviderUnavailable(f"groq returned {response.status_code}")

            payload = response.json()
            usage = payload.get("usage") or {}
            logger.info(
                "groq usage: prompt=%s output=%s total=%s",
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
                usage.get("total_tokens", "?"),
            )
            try:
                message = payload["choices"][0]["message"]
            except (KeyError, IndexError, TypeError) as caught:
                raise ProviderUnavailable("groq returned an unreadable response") from caught

            text = (message.get("content") or "").strip()
            if text:
                last_text = text
            raw_calls = message.get("tool_calls") or []
            if not raw_calls:
                if not last_text:
                    raise ProviderUnavailable("groq returned an empty response")
                return LLMResult(last_text, provider=self.name)

            messages.append(message)
            for raw in raw_calls:
                function = raw.get("function") or {}
                name = function.get("name") or ""
                arguments = _parse_tool_arguments(function.get("arguments"))
                logger.info("FitBot tool: %s(%s)", name, arguments)
                output = execute(name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": raw.get("id") or name,
                        "content": output,
                    }
                )

        return LLMResult(
            last_text or "I looked that up but could not finish the reply.",
            provider=self.name,
        )


def _parse_tool_arguments(raw) -> dict:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_dict(args) -> dict:
    if args is None:
        return {}
    if isinstance(args, dict):
        return dict(args)
    try:
        return dict(args)
    except (TypeError, ValueError):
        return {}


def _gemini_tool_calls(response) -> tuple[ToolCall, ...]:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ()
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    calls: list[ToolCall] = []
    for part in parts:
        fc = getattr(part, "function_call", None)
        if not fc or not getattr(fc, "name", None):
            continue
        calls.append(
            ToolCall(
                name=fc.name,
                arguments=_as_dict(getattr(fc, "args", None)),
                id=str(getattr(fc, "id", "") or ""),
            )
        )
    return tuple(calls)


class LLMChain:
    """Ask each configured provider in turn until one answers."""

    def __init__(self, providers: list) -> None:
        self.providers = providers
        self.cooldown_seconds = get_settings().llm_cooldown_seconds
        self._resume_at: dict[str, float] = {}

    @property
    def is_configured(self) -> bool:
        return any(provider.is_configured for provider in self.providers)

    def _available(self, provider) -> bool:
        if not provider.is_configured:
            return False
        resume_at = self._resume_at.get(provider.name, 0.0)
        if resume_at > time.monotonic():
            logger.debug("skipping %s, cooling down", provider.name)
            return False
        return True

    def _try_providers(self, call) -> LLMResult:
        if not self.is_configured:
            return LLMResult(NOT_CONFIGURED)

        for provider in self.providers:
            if not self._available(provider):
                continue
            try:
                return call(provider)
            except ProviderUnavailable as unavailable:
                if unavailable.exhausted:
                    self._resume_at[provider.name] = time.monotonic() + self.cooldown_seconds
                    logger.warning(
                        "%s is out of quota, skipping it for %ss",
                        provider.name,
                        self.cooldown_seconds,
                    )
                else:
                    logger.warning("%s failed: %s", provider.name, unavailable)

        logger.error("every configured provider refused the request")
        return LLMResult(ALL_PROVIDERS_DOWN)

    def generate(self, system_instruction: str, prompt: str) -> LLMResult:
        return self._try_providers(
            lambda provider: provider.generate(system_instruction, prompt)
        )

    def generate_with_tools(
        self,
        system_instruction: str,
        prompt: str,
        tools: Sequence[ToolSpec],
        execute: Callable[[str, dict], str],
        max_rounds: int = MAX_TOOL_ROUNDS,
    ) -> LLMResult:
        """Ask the model, run any tool calls it makes, and return the final text.

        Providers that do not implement tool calling fall back to a plain generate.
        """

        def call(provider):
            method = getattr(provider, "generate_with_tools", None)
            if method is None:
                return provider.generate(system_instruction, prompt)
            return method(
                system_instruction, prompt, tools, execute, max_rounds=max_rounds
            )

        return self._try_providers(call)


@lru_cache
def get_llm() -> LLMChain:
    """One chain per process, so the cooldown is remembered between requests."""
    return LLMChain([GeminiProvider(), GroqProvider()])
