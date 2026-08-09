"""Answers the database already holds.

Prices and class timings are facts, not opinions. FitBot is told never to invent them, so
sending these questions to a model costs a request from a small daily quota and produces a
worse answer than a two-line query. These replies are exact, instant and free.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import UNLIMITED_CLASS_QUOTA, ClassSchedule, MembershipPlan, utc_now

TIMETABLE_DAYS = 7
TIMETABLE_LIMIT = 12


def _rupees(paise: int) -> str:
    return f"Rs {paise / 100:,.0f}"


def _plan_line(plan: MembershipPlan) -> str:
    disciplines = plan.allowed_disciplines.replace(",", ", ")
    if plan.monthly_class_quota == UNLIMITED_CLASS_QUOTA:
        classes = "unlimited classes"
    elif plan.monthly_class_quota:
        classes = f"{plan.monthly_class_quota} classes a month"
    else:
        classes = "no class credits"

    extras = [classes, f"access to {disciplines}"]
    if plan.personalised_programme:
        extras.append("a trainer-written programme")
    if plan.priority_support:
        extras.append("priority support")

    return (
        f"- {plan.name}: {_rupees(plan.price_paise)} for {plan.duration_days} days. "
        f"Includes {', '.join(extras)}."
    )


def pricing(db: Session) -> str | None:
    plans = db.scalars(
        select(MembershipPlan)
        .where(MembershipPlan.active.is_(True))
        .order_by(MembershipPlan.price_paise)
    ).all()
    if not plans:
        return None
    lines = [_plan_line(plan) for plan in plans]
    return (
        "Here are our current packages:\n"
        + "\n".join(lines)
        + "\nYou can join from the Packages page, or ask me anything about which one fits you."
    )


def timetable(db: Session) -> str | None:
    now = utc_now()
    classes = db.scalars(
        select(ClassSchedule)
        .where(ClassSchedule.starts_at >= now)
        .where(ClassSchedule.starts_at <= now + timedelta(days=TIMETABLE_DAYS))
        .order_by(ClassSchedule.starts_at)
        .limit(TIMETABLE_LIMIT)
    ).all()
    if not classes:
        return None

    local = ZoneInfo(get_settings().display_timezone)
    lines = [
        f"- {item.name} ({item.discipline}) with {item.instructor}, "
        f"{item.starts_at.replace(tzinfo=ZoneInfo('UTC')).astimezone(local):%a %d %b, %I:%M %p}"
        for item in classes
    ]
    return (
        f"Here is what is on over the next {TIMETABLE_DAYS} days:\n"
        + "\n".join(lines)
        + "\nSign in and open your dashboard to book a place."
    )


ANSWERS = {"pricing": pricing, "timetable": timetable}


def answer(db: Session, kind: str | None) -> str | None:
    """Return the scripted reply for a front-desk question, or None to let the model answer."""
    builder = ANSWERS.get(kind or "")
    return builder(db) if builder else None
