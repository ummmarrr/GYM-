"""Text generation, spread across more than one provider.

Every free tier runs out. Rather than apologising to the member when Gemini's daily quota is
gone, the chain moves to the next provider and keeps answering. A provider that reports
exhaustion is skipped for a cooldown period so the next caller does not pay its timeout again.
"""

import logging
import time
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)

NOT_CONFIGURED = (
    "The AI coach is not configured yet. Add GEMINI_API_KEY or GROQ_API_KEY to your .env file, "
    "then restart the backend."
)
ALL_PROVIDERS_DOWN = (
    "I could not reach the coaching model just now. Please try again in a moment, or ask "
    "reception for help."
)


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str = "none"


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

    def generate(self, system_instruction: str, prompt: str) -> LLMResult:
        if not self.is_configured:
            return LLMResult(NOT_CONFIGURED)

        for provider in self.providers:
            if not self._available(provider):
                continue
            try:
                return provider.generate(system_instruction, prompt)
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


@lru_cache
def get_llm() -> LLMChain:
    """One chain per process, so the cooldown is remembered between requests."""
    return LLMChain([GeminiProvider(), GroqProvider()])
