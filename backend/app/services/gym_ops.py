"""Gym operations shared by FitBot tools and the MCP server.

The API layer stays the HTTP face. This module is the read/write surface any agent can call
without going through FastAPI, so Cursor (MCP) and FitBot cannot drift apart.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import ClassBooking, ClassSchedule, Role, User, utc_now
from app.services import analytics, front_desk
from app.services.entitlements import entitlements_for
from app.services.llm import get_llm
from app.services.rag import KnowledgeBase, RetrievedChunk

logger = logging.getLogger(__name__)

PUBLIC_DISCIPLINES = ("reception",)
KNOWN_DISCIPLINES = frozenset({"gym", "yoga", "mma", "reception"})
RETRIEVAL_LIMIT = 3
# One initial retrieve plus one reformulated retry. Locked / empty shelves never enter the loop.
MAX_RETRIEVAL_ATTEMPTS = 2

GRADE_SYSTEM = """You grade retrieved gym documents. Reply with JSON only, no markdown.
{"enough": true, "rewrite": ""}
enough is true if the passages can answer the member's question from the gym's own material.
If enough is false, rewrite is a short improved search query for the SAME topic.
Never name a different sport or discipline. Never invent file names."""


def readable_disciplines(allowed: tuple[str, ...] | None) -> tuple[str, ...]:
    """Which document shelves this caller may draw on."""
    return tuple(sorted({*PUBLIC_DISCIPLINES, *(allowed or ())}))


def pricing_text(db: Session) -> str:
    return front_desk.pricing(db) or "No packages are currently on sale."


def timetable_text(db: Session) -> str:
    return (
        front_desk.timetable(db)
        or "No classes are scheduled in the next 7 days. Answer generally, and do not invent times."
    )


def retrieve_chunks(
    db,
    query: str,
    discipline: str,
    allowed: tuple[str, ...],
    limit: int = RETRIEVAL_LIMIT,
) -> list[RetrievedChunk]:
    if discipline not in allowed:
        return []
    try:
        return KnowledgeBase(db).retrieve(query, (discipline,), limit=limit)
    except Exception:
        logger.exception("Retrieval failed, answering without documents")
        return []


def _clip_chunk(text: str, limit: int = 500) -> str:
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _render_chunks(chunks: list[RetrievedChunk]) -> str:
    lines = []
    for chunk in chunks:
        kind = getattr(chunk, "kind", None) or "text"
        label = f"[{chunk.source} p{chunk.page or '?'} | {kind}]"
        lines.append(f"{label} {_clip_chunk(chunk.text)}")
    return "\n".join(lines)


def parse_retrieval_grade(raw: str) -> tuple[bool, str]:
    """enough, rewrite. Unreadable replies keep the first retrieve (enough=True)."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return True, ""
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return True, ""
    if not isinstance(parsed, dict):
        return True, ""
    enough = bool(parsed.get("enough", True))
    rewrite = str(parsed.get("rewrite") or "").strip()[:200]
    if not enough and not rewrite:
        return True, ""
    return enough, rewrite


def grade_retrieval(question: str, chunks: list[RetrievedChunk]) -> tuple[bool, str]:
    """Ask the model whether these chunks answer the question. Skip if no provider."""
    provider = get_llm()
    if not provider.is_configured:
        return True, ""
    result = provider.generate(
        GRADE_SYSTEM,
        f"Question: {question}\n\nPassages:\n{_render_chunks(chunks)}",
    )
    return parse_retrieval_grade(result.text)


def search_documents(
    db: Session,
    query: str,
    discipline: str,
    allowed: tuple[str, ...],
) -> tuple[str, list[RetrievedChunk]]:
    """Return a model-facing string and the chunks that produced it.

    Filtering is inside retrieve(), so an excluded shelf can never shape the ranking.
    If the first pass looks weak, one reformulated retrieve runs on the same shelf only.
    """
    shelf = discipline if discipline in KNOWN_DISCIPLINES else "gym"
    if shelf not in allowed:
        return (
            f"LOCKED: their package does not include {shelf}. Answer generally from your own "
            "knowledge, then mention the package that unlocks our full material. Do not quote "
            "gym documents for this discipline.",
            [],
        )

    search_query = query.strip()
    chunks: list[RetrievedChunk] = []
    refined = False
    for attempt in range(MAX_RETRIEVAL_ATTEMPTS):
        chunks = retrieve_chunks(db, search_query, shelf, allowed)
        if not chunks:
            break
        if attempt >= MAX_RETRIEVAL_ATTEMPTS - 1:
            break
        enough, rewrite = grade_retrieval(query, chunks)
        if enough or not rewrite or rewrite.lower() == search_query.lower():
            break
        logger.info("agentic rag retry shelf=%s query=%r", shelf, rewrite)
        search_query = rewrite
        refined = True

    if not chunks:
        return (
            "No matching documents on this shelf. Answer from general coaching knowledge.",
            [],
        )
    header = "Retrieval was refined once.\n" if refined else ""
    return header + _render_chunks(chunks), chunks


def metrics_text(db: Session, keys: list[str] | None = None) -> str:
    """Only registry keys run. Anything else is dropped, same as the admin DataAgent."""
    chosen = keys or ["membership_overview", "revenue_summary"]
    metrics = analytics.run_metrics(db, chosen)
    if not metrics:
        catalogue = analytics.catalogue()
        return f"None of those keys are in the metric registry. Choose from:\n{catalogue}"
    return "\n\n".join(metric.as_text() for metric in metrics)


def metric_catalogue() -> str:
    return analytics.catalogue()


def _seat_counts(db: Session) -> dict[str, int]:
    return dict(
        db.execute(
            select(ClassBooking.class_id, func.count(ClassBooking.id)).group_by(
                ClassBooking.class_id
            )
        ).all()
    )


def list_upcoming_classes(db: Session, days: int = 7, limit: int = 12) -> str:
    now = utc_now()
    classes = db.scalars(
        select(ClassSchedule)
        .where(ClassSchedule.starts_at >= now)
        .where(ClassSchedule.starts_at <= now + timedelta(days=days))
        .order_by(ClassSchedule.starts_at)
        .limit(limit)
    ).all()
    if not classes:
        return "No upcoming classes in that window."
    taken = _seat_counts(db)
    lines = []
    for item in classes:
        seats_left = max(item.capacity - taken.get(item.id, 0), 0)
        lines.append(
            f"- id={item.id} {item.name} ({item.discipline}) with {item.instructor} "
            f"at {item.starts_at:%a %d %b %H:%M} UTC, {seats_left} seats left"
        )
    return "\n".join(lines)


def book_class_for_email(db: Session, member_email: str, class_id: str) -> str:
    """Book a class for a member, with the same entitlement checks as the HTTP API."""
    user = db.scalars(select(User).where(User.email == member_email.lower().strip())).first()
    if user is None:
        return f"No member found with email {member_email}."
    if user.role != Role.MEMBER:
        return "Only member accounts can be booked into classes this way."
    if not user.active:
        return "That account is deactivated."

    session = db.get(ClassSchedule, class_id)
    if session is None:
        return "Class not found. Call list_upcoming_classes to get valid ids."

    allowed, reason = entitlements_for(db, user).may_book(session.discipline)
    if not allowed:
        return reason

    already = db.scalars(
        select(ClassBooking).where(
            ClassBooking.class_id == class_id, ClassBooking.member_id == user.id
        )
    ).first()
    if already:
        return f"{user.full_name} is already booked on {session.name}."

    seats_taken = _seat_counts(db).get(class_id, 0)
    if seats_taken >= session.capacity:
        return "This class is full."

    db.add(ClassBooking(class_id=class_id, member_id=user.id))
    db.commit()
    return (
        f"Booked {session.name} for {user.full_name} "
        f"on {session.starts_at:%d %b, %H:%M} UTC."
    )
