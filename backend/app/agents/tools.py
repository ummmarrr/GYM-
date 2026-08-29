"""FitBot's tool menu.

The model picks from these. Safety, login and upgrade prompts stay as code branches in the
graph — those are permission decisions, not something a prompt can be talked out of.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.gym_ops import (
    pricing_text,
    readable_disciplines,
    search_documents,
    timetable_text,
)
from app.services.llm import ToolSpec
from app.services.rag import RetrievedChunk

FITBOT_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_pricing",
        description=(
            "Return the live membership packages and prices from the database. "
            "Always call this instead of inventing a price."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="get_timetable",
        description=(
            "Return upcoming classes for the next 7 days from the database. "
            "Always call this instead of inventing a class time."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="search_knowledge",
        description=(
            "Search the gym's approved PDFs with hybrid retrieval (keyword + semantic) and "
            "agentic retry. Pass the coaching discipline the question is about. Documents "
            "outside the caller's package are never returned. Weak first hits may be retried "
            "once with a rewritten query on the same shelf."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query, usually the member's question.",
                },
                "discipline": {
                    "type": "string",
                    "enum": ["gym", "yoga", "mma", "reception"],
                    "description": "Which document shelf to search.",
                },
            },
            "required": ["query"],
        },
    ),
    ToolSpec(
        name="check_entitlement",
        description=(
            "Return what the signed-in caller's package allows: disciplines, class quota, "
            "expiry. Call this for questions about 'my plan', bookings remaining, or upgrades."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="request_login",
        description=(
            "Show the in-chat sign-in form. Use when a visitor asks about their own account. "
            "Never ask for a password in the chat."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="request_signup",
        description=(
            "Show the in-chat join form. Use when a visitor wants to create an account. "
            "Never ask for a password in the chat."
        ),
        parameters={"type": "object", "properties": {}},
    ),
)


@dataclass
class ToolContext:
    db: object
    entitlements: str = ""
    is_authenticated: bool = False
    allowed_disciplines: tuple[str, ...] = ()
    sources: list[RetrievedChunk] = field(default_factory=list)
    action: str = "none"


def execute_fitbot_tool(name: str, arguments: dict, ctx: ToolContext) -> str:
    """Run one tool. Unknown names return an error string; they never raise into the graph."""
    args = arguments or {}
    if name == "get_pricing":
        return pricing_text(ctx.db)
    if name == "get_timetable":
        return timetable_text(ctx.db)
    if name == "search_knowledge":
        query = str(args.get("query") or "").strip()
        discipline = str(args.get("discipline") or "gym").strip().lower()
        if not query:
            return "search_knowledge needs a query."
        allowed = readable_disciplines(ctx.allowed_disciplines)
        text, chunks = search_documents(ctx.db, query, discipline, allowed)
        ctx.sources.extend(chunks)
        return text
    if name == "check_entitlement":
        if not ctx.is_authenticated:
            ctx.action = "login"
            return (
                "The caller is signed out. Use request_login so they can sign in. "
                "Do not guess their package."
            )
        return ctx.entitlements or "Signed in, but no package details are available."
    if name == "request_login":
        if ctx.is_authenticated:
            return "The caller is already signed in. Do not show a login form."
        ctx.action = "login"
        return (
            "The widget will render a real sign-in form. Tell them to use it. "
            "Never ask for a password, OTP or card number in the chat."
        )
    if name == "request_signup":
        if ctx.is_authenticated:
            return "The caller already has an account."
        ctx.action = "signup"
        return (
            "The widget will render a real sign-up form. Tell them to use it. "
            "Never ask for a password in the chat."
        )
    return f"Unknown tool {name!r}. Choose from the provided tools."


# Re-exported so existing tests keep importing the ladder helper from this module.
__all__ = [
    "FITBOT_TOOLS",
    "ToolContext",
    "execute_fitbot_tool",
    "readable_disciplines",
]
