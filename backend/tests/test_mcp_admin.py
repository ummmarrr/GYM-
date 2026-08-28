"""Admin MCP auth: login once, then ask with a session token — never password on every turn."""

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, create_mcp_admin_token
from app.db import Role
from app.mcp_admin import (
    _require_admin_session,
    admin_login,
    ask_copilot,
    sample_questions,
)
from app.services.llm import LLMResult
from tests.conftest import make_user


@pytest.fixture
def mcp_db(db_session, monkeypatch):
    """Point the MCP server at the same in-memory DB the fixtures write to."""
    TestingSession = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("app.mcp_admin.SessionLocal", TestingSession)
    return db_session


def test_sample_questions_need_no_auth():
    text = sample_questions()
    assert "DataAgent" in text
    assert "AdvisorAgent" in text


def test_admin_login_rejects_wrong_password(mcp_db):
    make_user(mcp_db, "boss@example.com", Role.ADMIN, password="CorrectHorse1")
    result = admin_login("boss@example.com", "wrong-password")
    assert "Login failed" in result
    assert "session_token=" not in result


def test_admin_login_rejects_a_member(mcp_db):
    make_user(mcp_db, "member@example.com", Role.MEMBER)
    result = admin_login("member@example.com", "Password123")
    assert "Login failed" in result


def test_admin_login_returns_a_session_token(mcp_db):
    admin = make_user(mcp_db, "boss@example.com", Role.ADMIN, password="CorrectHorse1")
    result = admin_login(admin.email, "CorrectHorse1")
    assert "session_token=" in result
    token = result.split("session_token=", 1)[1].split()[0]
    user = _require_admin_session(token)
    assert user.id == admin.id


def test_ask_copilot_requires_a_valid_mcp_token(mcp_db):
    admin = make_user(mcp_db, "boss@example.com", Role.ADMIN)
    # Ordinary web JWT has no purpose=mcp_admin claim.
    web_token = create_access_token(admin.id, Role.ADMIN.value)
    result = ask_copilot("How is revenue?", web_token)
    assert "MCP admin session" in result or "admin_login" in result


def test_ask_copilot_accepts_an_mcp_token(mcp_db, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.LLMChain.is_configured",
        property(lambda self: False),
    )
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate",
        lambda self, system, prompt: LLMResult(text="All steady."),
    )
    admin = make_user(mcp_db, "boss@example.com", Role.ADMIN)
    token = create_mcp_admin_token(admin.id)
    result = ask_copilot("What needs my attention this week?", token)
    assert "Login failed" not in result
    assert "Invalid" not in result
    assert len(result) > 20


def test_ask_copilot_rejects_a_member_token(mcp_db):
    member = make_user(mcp_db, "member@example.com", Role.MEMBER)
    # Even a forged-looking MCP token for a member must fail the DB role check.
    token = create_mcp_admin_token(member.id)
    result = ask_copilot("How is revenue?", token)
    assert "Only admin" in result
