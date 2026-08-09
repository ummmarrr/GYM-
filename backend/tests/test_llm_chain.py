"""The provider chain: what happens as each free tier runs out."""

from app.services.llm import (
    ALL_PROVIDERS_DOWN,
    NOT_CONFIGURED,
    LLMChain,
    LLMResult,
    ProviderUnavailable,
)


class FakeProvider:
    def __init__(self, name, *, configured=True, text=None, error=None):
        self.name = name
        self.is_configured = configured
        self._text = text
        self._error = error
        self.calls = 0

    def generate(self, system_instruction, prompt):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return LLMResult(self._text, provider=self.name)


def exhausted(name="gemini"):
    return FakeProvider(name, error=ProviderUnavailable("429", exhausted=True))


def test_the_first_working_provider_answers():
    first = FakeProvider("gemini", text="from gemini")
    second = FakeProvider("groq", text="from groq")

    result = LLMChain([first, second]).generate("sys", "prompt")

    assert result.text == "from gemini"
    assert second.calls == 0


def test_an_exhausted_provider_falls_through_to_the_next_one():
    groq = FakeProvider("groq", text="from groq")

    result = LLMChain([exhausted(), groq]).generate("sys", "prompt")

    assert result.text == "from groq"
    assert result.provider == "groq"


def test_a_provider_that_reported_exhaustion_is_not_asked_again():
    """Otherwise every later request pays its timeout before falling through."""
    gemini = exhausted()
    groq = FakeProvider("groq", text="from groq")
    chain = LLMChain([gemini, groq])

    chain.generate("sys", "prompt")
    chain.generate("sys", "prompt")

    assert gemini.calls == 1
    assert groq.calls == 2


def test_a_one_off_failure_does_not_sideline_a_provider():
    """A timeout is not a quota. The provider may well work on the next request."""
    gemini = FakeProvider("gemini", error=ProviderUnavailable("connection reset"))
    groq = FakeProvider("groq", text="from groq")
    chain = LLMChain([gemini, groq])

    chain.generate("sys", "prompt")
    chain.generate("sys", "prompt")

    assert gemini.calls == 2


def test_unconfigured_providers_are_skipped():
    gemini = FakeProvider("gemini", configured=False)
    groq = FakeProvider("groq", text="from groq")

    assert LLMChain([gemini, groq]).generate("sys", "prompt").text == "from groq"
    assert gemini.calls == 0


def test_no_keys_at_all_asks_the_owner_to_configure_one():
    chain = LLMChain([FakeProvider("gemini", configured=False)])

    assert chain.generate("sys", "prompt").text == NOT_CONFIGURED


def test_when_every_provider_refuses_the_member_gets_an_apology_not_an_error():
    chain = LLMChain([exhausted("gemini"), exhausted("groq")])

    assert chain.generate("sys", "prompt").text == ALL_PROVIDERS_DOWN


def test_a_lapsed_cooldown_lets_the_provider_back_in():
    gemini = exhausted()
    chain = LLMChain([gemini, FakeProvider("groq", text="from groq")])
    chain.cooldown_seconds = 0

    chain.generate("sys", "prompt")
    chain.generate("sys", "prompt")

    assert gemini.calls == 2
