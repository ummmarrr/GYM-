"""The public endpoints cost money or invite guessing, so they are capped per caller."""

import pytest

from app.core.config import get_settings
from app.core.rate_limit import SlidingWindow
from app.db import Role
from app.services.llm import LLMResult
from tests.conftest import make_user

settings = get_settings()


@pytest.fixture
def no_model(monkeypatch):
    """Answer instantly without a provider, so these tests measure the limiter alone."""
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate", lambda self, system, user: LLMResult("Sure.")
    )
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate_with_tools",
        lambda self, system, prompt, tools, execute, max_rounds=4: LLMResult("Sure."),
    )


def test_chat_stops_a_flood_from_one_caller(client, no_model):
    allowed = settings.chat_rate_limit
    for _ in range(allowed):
        assert client.post("/api/fitbot/chat", json={"message": "hi"}).status_code == 200

    blocked = client.post("/api/fitbot/chat", json={"message": "hi"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_login_guessing_is_capped(client, db_session):
    make_user(db_session, "victim@example.com", Role.MEMBER)

    for _ in range(settings.login_rate_limit):
        response = client.post(
            "/api/auth/login", json={"email": "victim@example.com", "password": "wrong-guess"}
        )
        assert response.status_code == 401

    # The correct password is refused too: the limit is on the caller, not on the outcome.
    blocked = client.post(
        "/api/auth/login", json={"email": "victim@example.com", "password": "Password123"}
    )
    assert blocked.status_code == 429


def test_signup_flooding_is_capped(client):
    for index in range(settings.register_rate_limit):
        response = client.post(
            "/api/auth/register",
            json={
                "email": f"new{index}@example.com",
                "full_name": "New Person",
                "password": "Password123",
            },
        )
        assert response.status_code == 201

    blocked = client.post(
        "/api/auth/register",
        json={"email": "one-too-many@example.com", "full_name": "Nope", "password": "Password123"},
    )
    assert blocked.status_code == 429


def test_callers_are_counted_separately():
    window = SlidingWindow()
    assert window.check("chat", "1.1.1.1", limit=1, window=60) is None
    assert window.check("chat", "1.1.1.1", limit=1, window=60) is not None
    # A different address still has its own allowance.
    assert window.check("chat", "2.2.2.2", limit=1, window=60) is None


def test_allowance_returns_once_the_window_passes(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: clock["now"])

    window = SlidingWindow()
    assert window.check("chat", "1.1.1.1", limit=2, window=60) is None
    assert window.check("chat", "1.1.1.1", limit=2, window=60) is None

    wait = window.check("chat", "1.1.1.1", limit=2, window=60)
    assert wait == pytest.approx(60)

    clock["now"] += 61
    assert window.check("chat", "1.1.1.1", limit=2, window=60) is None


def test_the_proxy_header_identifies_the_caller(client, no_model):
    for _ in range(settings.chat_rate_limit):
        assert (
            client.post(
                "/api/fitbot/chat",
                json={"message": "hi"},
                headers={"X-Forwarded-For": "9.9.9.9, 10.0.0.1"},
            ).status_code
            == 200
        )

    assert (
        client.post(
            "/api/fitbot/chat",
            json={"message": "hi"},
            headers={"X-Forwarded-For": "9.9.9.9"},
        ).status_code
        == 429
    )
    # A different visitor behind the same Render proxy is unaffected.
    assert (
        client.post(
            "/api/fitbot/chat",
            json={"message": "hi"},
            headers={"X-Forwarded-For": "8.8.8.8"},
        ).status_code
        == 200
    )
