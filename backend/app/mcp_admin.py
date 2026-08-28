"""Admin-only MCP server for the multi-agent Copilot.

Auth model (deliberate — never put a password on every question):
1. Call admin_login(email, password) once. On success you get a short-lived session_token.
2. Call ask_copilot(question, session_token) with that token. Role is re-checked from the DB.
3. Call admin_logout(session_token) when finished (optional; the token also expires).

This module is shipped as code in the repo. Do not wire it into Cursor / Claude Desktop on a
shared machine — run it only on a machine you control.

    python -m app.mcp_admin
"""

from __future__ import annotations

from jwt import InvalidTokenError
from mcp.server.mcpserver import MCPServer
from sqlalchemy import select

from app.agents.orchestrator import workflow as orchestrator_workflow
from app.core.security import (
    create_mcp_admin_token,
    decode_access_token,
    verify_password,
)
from app.db import Role, SessionLocal, User

mcp = MCPServer(
    "Master GYM Admin Copilot",
    instructions=(
        "Admin-only multi-agent orchestrator for Master GYM. "
        "First call admin_login with an admin email and password. "
        "Then call ask_copilot with the returned session_token. "
        "Never put the password on ask_copilot. Never invent numbers — "
        "the Copilot only delegates to DataAgent and AdvisorAgent."
    ),
)


def _require_admin_session(session_token: str) -> User:
    """Decode the MCP token and re-read role from the database (token role is never trusted)."""
    try:
        payload = decode_access_token(session_token)
    except InvalidTokenError as exc:
        raise ValueError("Invalid or expired session_token. Call admin_login again.") from exc

    if payload.get("purpose") != "mcp_admin":
        raise ValueError("This token is not an MCP admin session. Call admin_login.")

    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Malformed session_token.")

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.active:
            raise ValueError("Account not found or deactivated.")
        if user.role != Role.ADMIN:
            raise ValueError("Only admin accounts may use this MCP server.")
        # Detach identity we need after the session closes.
        db.expunge(user)
        return user
    finally:
        db.close()


@mcp.tool()
def admin_login(email: str, password: str) -> str:
    """Verify an admin account and return a short-lived session_token.

    Pass the token to ask_copilot. Do not send the password on later calls.
    """
    db = SessionLocal()
    try:
        user = db.scalars(select(User).where(User.email == email.lower().strip())).first()
        # Same wording for unknown email and wrong password — no account enumeration.
        if (
            user is None
            or not user.active
            or user.role != Role.ADMIN
            or not verify_password(password, user.password_hash)
        ):
            return (
                "Login failed. Check the admin email and password. "
                "Only active admin accounts may use this server."
            )
        token = create_mcp_admin_token(user.id)
        return (
            f"Signed in as {user.full_name} ({user.email}). "
            f"session_token={token}\n"
            "Pass this session_token to ask_copilot. It expires in about 60 minutes."
        )
    finally:
        db.close()


@mcp.tool()
def ask_copilot(question: str, session_token: str) -> str:
    """Ask the multi-agent Copilot. Requires a session_token from admin_login.

    The supervisor may call DataAgent and/or AdvisorAgent. Numbers always come from vetted
    queries, never from model-written SQL.
    """
    try:
        user = _require_admin_session(session_token)
    except ValueError as exc:
        return str(exc)

    trimmed = question.strip()
    if len(trimmed) < 3:
        return "Ask a real question (at least a few words)."

    db = SessionLocal()
    try:
        state = orchestrator_workflow.invoke({"question": trimmed, "db": db})
        agents = ", ".join(state.get("agents_used") or []) or "none"
        return (
            f"{state['answer']}\n\n"
            f"(asked by {user.email}; agents used: {agents})"
        )
    finally:
        db.close()


@mcp.tool()
def admin_logout(session_token: str) -> str:
    """Acknowledge logout. Tokens are short-lived JWTs; discarding the token is enough."""
    try:
        _require_admin_session(session_token)
    except ValueError as exc:
        return str(exc)
    return (
        "Logged out of the MCP session. Discard the session_token. "
        "Call admin_login again to continue."
    )


@mcp.tool()
def sample_questions() -> str:
    """Example questions the Copilot can answer. No auth required."""
    return (
        "Data (DataAgent):\n"
        "- How much revenue have we made?\n"
        "- Whose membership expires soon?\n"
        "- Are our classes filling up?\n"
        "- Which members have gone quiet?\n\n"
        "Advice (AdvisorAgent):\n"
        "- What needs my attention this week?\n"
        "- Give me the owner's briefing.\n\n"
        "Both (orchestrator calls both):\n"
        "- Why might members be leaving and what should I do?\n"
        "- Summarise revenue risk and the top actions."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
