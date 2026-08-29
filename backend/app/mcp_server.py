"""MCP server for Master GYM.

Exposes the same gym operations FitBot uses as Model Context Protocol tools, so Cursor,
Claude Desktop or any MCP client can query prices, the timetable, the knowledge base and
admin metrics — and book a class — without going through the web app.

Run from the backend directory:

    python -m app.mcp_server

Or after install:

    master-gym-mcp
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from app.db import SessionLocal
from app.services import gym_ops

mcp = MCPServer(
    "Master GYM",
    instructions=(
        "Tools for the Master GYM platform. Prices and class times come from the database, "
        "never invent them. Metric keys must exist in the vetted registry. "
        "search_knowledge is filtered by discipline. book_class enforces the member's package."
    ),
)


@mcp.tool()
def get_pricing() -> str:
    """Live membership packages and prices from the database. Never invent a price."""
    db = SessionLocal()
    try:
        return gym_ops.pricing_text(db)
    finally:
        db.close()


@mcp.tool()
def get_timetable() -> str:
    """Upcoming classes for the next 7 days. Never invent a class time."""
    db = SessionLocal()
    try:
        return gym_ops.timetable_text(db)
    finally:
        db.close()


@mcp.tool()
def search_knowledge(query: str, discipline: str = "gym") -> str:
    """Search admin-uploaded PDFs with hybrid (keyword + semantic) + agentic retry.

    Staff MCP access can read every discipline shelf. Weak first hits may be retrieved once
    more with a rewritten query; the shelf never widens.
    """
    db = SessionLocal()
    try:
        text, _chunks = gym_ops.search_documents(
            db, query, discipline, gym_ops.readable_disciplines(("gym", "yoga", "mma"))
        )
        return text
    finally:
        db.close()


@mcp.tool()
def list_metric_keys() -> str:
    """The vetted analytics keys the model may request. Anything else is ignored."""
    return gym_ops.metric_catalogue()


@mcp.tool()
def get_gym_metrics(keys: str = "membership_overview,revenue_summary") -> str:
    """Run vetted metric queries. Pass a comma-separated list of keys from list_metric_keys."""
    chosen = [key.strip() for key in keys.split(",") if key.strip()]
    db = SessionLocal()
    try:
        return gym_ops.metrics_text(db, chosen)
    finally:
        db.close()


@mcp.tool()
def list_upcoming_classes() -> str:
    """Upcoming classes with ids, so book_class can be called with a real class_id."""
    db = SessionLocal()
    try:
        return gym_ops.list_upcoming_classes(db)
    finally:
        db.close()


@mcp.tool()
def book_class(member_email: str, class_id: str) -> str:
    """Book a class for a member. Enforces package entitlements, capacity and duplicates."""
    db = SessionLocal()
    try:
        return gym_ops.book_class_for_email(db, member_email, class_id)
    finally:
        db.close()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
