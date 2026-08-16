"""FitBot chat endpoint. Works for signed-out visitors and for members alike."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.workflow import classify_front_desk, workflow
from app.api.deps import get_current_user, get_optional_user
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.db import ChatMessage, Conversation, FitnessProfile, Role, User, get_db
from app.schemas import ChatRequest, ChatResponse, SourceCitation
from app.services import front_desk
from app.services.entitlements import entitlements_for

router = APIRouter(prefix="/fitbot", tags=["fitbot"])

settings = get_settings()
# Anyone can reach this endpoint and each call spends LLM quota, so it is capped per caller.
chat_limit = rate_limit("chat", settings.chat_rate_limit, settings.chat_rate_window_seconds)

# Whatever is sent here is resent to the model on every turn. Four turns is enough to follow a
# thread, and clipping each one stops a single long coaching reply from dominating the prompt.
HISTORY_TURNS = 4
HISTORY_CHARS_PER_TURN = 200


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _describe_entitlements(db: Session, user: User | None) -> str:
    if user is None:
        return "Not a member yet — they are browsing the public site."
    if user.role in (Role.ADMIN, Role.TRAINER):
        return f"Master GYM staff ({user.role.value}). Full access, no package involved."

    ent = entitlements_for(db, user)
    if not ent.has_active_membership:
        return "Signed in, but has no active package right now."

    disciplines = ", ".join(ent.allowed_disciplines) or "gym"
    quota = "unlimited" if ent.monthly_class_quota < 0 else str(ent.monthly_class_quota)
    # Staff and complimentary memberships have no end date, so this stays optional.
    validity = (
        f"valid until {ent.expires_on:%d %b %Y} ({ent.days_remaining} days left)"
        if ent.expires_on
        else "no expiry date"
    )
    return (
        f"{ent.plan_name} package, {validity}. Access: {disciplines}. "
        f"Class quota this month: {ent.classes_booked_this_month} used of {quota}."
    )


def _describe_profile(db: Session, user: User | None) -> str:
    if user is None:
        return ""
    profile = db.get(FitnessProfile, user.id)
    if profile is None:
        return "No fitness profile saved yet."
    parts = [
        f"goal: {profile.goal}" if profile.goal else "",
        f"experience: {profile.experience_level}" if profile.experience_level else "",
        f"limitations: {profile.injuries_or_limits}" if profile.injuries_or_limits else "",
        f"equipment: {profile.equipment_access}" if profile.equipment_access else "",
    ]
    return ", ".join(part for part in parts if part) or "No fitness profile saved yet."


def _load_conversation(db: Session, conversation_id: str | None, user: User | None) -> Conversation:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        # A conversation started while signed in must not be readable by anyone else.
        if conversation.user_id and (user is None or conversation.user_id != user.id):
            raise HTTPException(status_code=403, detail="This conversation is not yours.")
        return conversation

    conversation = Conversation(user_id=user.id if user else None)
    db.add(conversation)
    db.flush()
    return conversation


def _history(db: Session, conversation_id: str) -> str:
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(HISTORY_TURNS)
    ).all()
    return "\n".join(
        f"{m.sender}: {_clip(m.content, HISTORY_CHARS_PER_TURN)}" for m in reversed(messages)
    )


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(chat_limit)])
def chat(
    payload: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)],
):
    conversation = _load_conversation(db, payload.conversation_id, user)

    # A visitor who signs in mid-chat keeps their conversation.
    if user is not None and conversation.user_id is None:
        conversation.user_id = user.id

    ent = entitlements_for(db, user) if user else None
    # Read prices and timings here, where the session lives, rather than inside the graph.
    scripted = front_desk.answer(db, classify_front_desk(payload.message))
    state = workflow.invoke(
        {
            "message": payload.message,
            "history": _history(db, conversation.id),
            "display_name": user.full_name if user else "",
            "role": user.role.value if user else "visitor",
            "is_authenticated": user is not None,
            "can_personalise": bool(ent and ent.personalised_programme),
            "allowed_disciplines": ent.allowed_disciplines if ent else (),
            "entitlements": _describe_entitlements(db, user),
            "profile": _describe_profile(db, user),
            "scripted": scripted or "",
            "language": payload.language,
            "db": db,
        }
    )

    sources = [
        SourceCitation(source=chunk.source, page=chunk.page, excerpt=chunk.text[:200])
        for chunk in state.get("sources", [])
    ]
    db.add(ChatMessage(conversation_id=conversation.id, sender="user", content=payload.message))
    db.add(
        ChatMessage(
            conversation_id=conversation.id,
            sender="fitbot",
            content=state["answer"],
            sources_json=json.dumps([s.model_dump() for s in sources]) if sources else None,
        )
    )
    db.commit()

    return ChatResponse(
        conversation_id=conversation.id,
        answer=state["answer"],
        route=state.get("route", "gym"),
        sources=sources,
        needs_human_handoff=state.get("needs_human_handoff", False),
        action=state.get("action", "none"),
    )


@router.get("/conversations/{conversation_id}")
def transcript(
    conversation_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
    ).all()
    return {
        "conversation_id": conversation_id,
        "messages": [
            {"sender": m.sender, "content": m.content, "created_at": m.created_at} for m in messages
        ],
    }
