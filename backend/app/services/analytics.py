"""Deterministic analytics for the admin console.

Every number the data agent quotes is produced here by a real query. The model only chooses
which of these metrics to look at and explains the result — it never writes SQL and never
invents a figure. That keeps password hashes and private chat transcripts unreachable, and
means a hallucination can never turn into a wrong number on the dashboard.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import (
    ChatMessage,
    ClassBooking,
    ClassSchedule,
    Conversation,
    FitnessProfile,
    KnowledgeDocument,
    Membership,
    MembershipPlan,
    Programme,
    Role,
    User,
)

DISCIPLINES = ("gym", "yoga", "mma")
RENEWAL_WINDOW_DAYS = 14
IDLE_WINDOW_DAYS = 30


@dataclass(frozen=True)
class Metric:
    key: str
    title: str
    headline: str
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)

    def as_text(self) -> str:
        """Rendered for the model. Compact, and never more than the rows we actually have."""
        lines = [f"### {self.title}", self.headline]
        if self.rows and self.columns:
            lines.append(" | ".join(self.columns))
            for row in self.rows:
                lines.append(" | ".join(str(row.get(column, "")) for column in self.columns))
        return "\n".join(lines)


def rupees(paise: int) -> str:
    return f"Rs {paise / 100:,.0f}"


def _today() -> date:
    return date.today()


def _midnight(value: date) -> datetime:
    return datetime.combine(value, time.min)


def _active_membership_rows(db: Session):
    return db.execute(
        select(User, Membership, MembershipPlan)
        .join(Membership, Membership.user_id == User.id)
        .join(MembershipPlan, MembershipPlan.id == Membership.plan_id)
        .where(Membership.status == "active", Membership.expires_on >= _today())
    ).all()


# --- Metric implementations ----------------------------------------------


def membership_overview(db: Session) -> Metric:
    total_members = db.scalar(select(func.count(User.id)).where(User.role == Role.MEMBER)) or 0
    active = _active_membership_rows(db)
    active_ids = {user.id for user, _, _ in active}

    ever_subscribed = set(
        db.scalars(
            select(Membership.user_id)
            .join(User, User.id == Membership.user_id)
            .where(User.role == Role.MEMBER)
        ).all()
    )
    lapsed = len(ever_subscribed - active_ids)
    never = max(total_members - len(ever_subscribed), 0)

    by_tier: dict[str, int] = defaultdict(int)
    for _, _, plan in active:
        by_tier[plan.name] += 1

    rows = [{"package": name, "active members": count} for name, count in sorted(by_tier.items())]
    return Metric(
        key="membership_overview",
        title="Membership overview",
        headline=(
            f"{total_members} members registered. {len(active_ids)} hold an active package, "
            f"{lapsed} have lapsed, {never} never subscribed."
        ),
        columns=["package", "active members"],
        rows=rows,
    )


def revenue_summary(db: Session) -> Metric:
    rows_raw = db.execute(
        select(MembershipPlan.name, MembershipPlan.price_paise, Membership.created_at).join(
            Membership, Membership.plan_id == MembershipPlan.id
        )
    ).all()

    total = sum(price for _, price, _ in rows_raw)
    cutoff = datetime.now() - timedelta(days=30)
    last_30 = sum(price for _, price, created in rows_raw if created and created >= cutoff)

    grouped: dict[str, list[int]] = defaultdict(list)
    for name, price, _ in rows_raw:
        grouped[name].append(price)

    rows = [
        {"package": name, "sold": len(prices), "revenue": rupees(sum(prices))}
        for name, prices in sorted(grouped.items(), key=lambda item: -sum(item[1]))
    ]
    return Metric(
        key="revenue_summary",
        title="Revenue",
        headline=(
            f"{rupees(total)} billed across {len(rows_raw)} memberships, "
            f"{rupees(last_30)} of that in the last 30 days."
        ),
        columns=["package", "sold", "revenue"],
        rows=rows,
    )


def signup_trend(db: Session) -> Metric:
    since = _midnight(_today().replace(day=1)) - timedelta(days=150)
    created = db.scalars(
        select(User.created_at).where(User.role == Role.MEMBER, User.created_at >= since)
    ).all()

    buckets: dict[str, int] = defaultdict(int)
    for value in created:
        buckets[value.strftime("%Y-%m")] += 1

    months: list[str] = []
    cursor = _today().replace(day=1)
    for _ in range(6):
        months.append(cursor.strftime("%Y-%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()

    rows = [{"month": month, "new members": buckets.get(month, 0)} for month in months]
    this_month = rows[-1]["new members"] if rows else 0
    last_month = rows[-2]["new members"] if len(rows) > 1 else 0
    direction = "up" if this_month > last_month else "down" if this_month < last_month else "flat"

    return Metric(
        key="signup_trend",
        title="Signup trend",
        headline=(
            f"{this_month} new members this month against {last_month} last month ({direction})."
        ),
        columns=["month", "new members"],
        rows=rows,
    )


def expiring_soon(db: Session) -> Metric:
    horizon = _today() + timedelta(days=RENEWAL_WINDOW_DAYS)
    rows_raw = db.execute(
        select(User.full_name, User.email, MembershipPlan.name, Membership.expires_on)
        .join(Membership, Membership.user_id == User.id)
        .join(MembershipPlan, MembershipPlan.id == Membership.plan_id)
        .where(
            Membership.status == "active",
            Membership.expires_on >= _today(),
            Membership.expires_on <= horizon,
        )
        .order_by(Membership.expires_on)
    ).all()

    rows = [
        {
            "member": name,
            "email": email,
            "package": plan,
            "expires": expires.strftime("%d %b %Y"),
            "days left": (expires - _today()).days,
        }
        for name, email, plan, expires in rows_raw
    ]
    return Metric(
        key="expiring_soon",
        title=f"Renewals due in {RENEWAL_WINDOW_DAYS} days",
        headline=f"{len(rows)} memberships expire within {RENEWAL_WINDOW_DAYS} days.",
        columns=["member", "package", "expires", "days left"],
        rows=rows,
    )


def class_utilisation(db: Session) -> Metric:
    sessions = db.scalars(select(ClassSchedule)).all()
    booked_counts = dict(
        db.execute(
            select(ClassBooking.class_id, func.count(ClassBooking.id)).group_by(
                ClassBooking.class_id
            )
        ).all()
    )

    grouped: dict[str, dict[str, int]] = defaultdict(
        lambda: {"sessions": 0, "seats": 0, "booked": 0}
    )
    for session in sessions:
        bucket = grouped[session.discipline]
        bucket["sessions"] += 1
        bucket["seats"] += session.capacity
        bucket["booked"] += booked_counts.get(session.id, 0)

    rows = []
    for discipline in DISCIPLINES:
        bucket = grouped.get(discipline)
        if not bucket:
            rows.append(
                {"discipline": discipline, "sessions": 0, "seats": 0, "booked": 0, "fill": "n/a"}
            )
            continue
        fill = round(100 * bucket["booked"] / bucket["seats"]) if bucket["seats"] else 0
        rows.append(
            {
                "discipline": discipline,
                "sessions": bucket["sessions"],
                "seats": bucket["seats"],
                "booked": bucket["booked"],
                "fill": f"{fill}%",
            }
        )

    total_seats = sum(bucket["seats"] for bucket in grouped.values())
    total_booked = sum(bucket["booked"] for bucket in grouped.values())
    overall = round(100 * total_booked / total_seats) if total_seats else 0
    return Metric(
        key="class_utilisation",
        title="Class utilisation",
        headline=(
            f"{len(sessions)} classes on the timetable, {total_booked} of {total_seats} seats "
            f"booked ({overall}% overall)."
        ),
        columns=["discipline", "sessions", "seats", "booked", "fill"],
        rows=rows,
    )


def trainer_load(db: Session) -> Metric:
    trainers = db.scalars(select(User).where(User.role == Role.TRAINER)).all()
    assigned = dict(
        db.execute(
            select(FitnessProfile.assigned_trainer_id, func.count(FitnessProfile.user_id))
            .where(FitnessProfile.assigned_trainer_id.isnot(None))
            .group_by(FitnessProfile.assigned_trainer_id)
        ).all()
    )
    programmes = dict(
        db.execute(
            select(Programme.trainer_id, func.count(Programme.id)).group_by(Programme.trainer_id)
        ).all()
    )
    classes = dict(
        db.execute(
            select(ClassSchedule.trainer_id, func.count(ClassSchedule.id))
            .where(ClassSchedule.trainer_id.isnot(None))
            .group_by(ClassSchedule.trainer_id)
        ).all()
    )

    rows = [
        {
            "trainer": trainer.full_name,
            "members": assigned.get(trainer.id, 0),
            "programmes": programmes.get(trainer.id, 0),
            "classes": classes.get(trainer.id, 0),
        }
        for trainer in sorted(trainers, key=lambda item: -assigned.get(item.id, 0))
    ]
    return Metric(
        key="trainer_load",
        title="Trainer workload",
        headline=(
            f"{len(trainers)} trainers covering {sum(assigned.values())} assigned members."
            if trainers
            else "No trainers on the roster yet."
        ),
        columns=["trainer", "members", "programmes", "classes"],
        rows=rows,
    )


def unassigned_members(db: Session) -> Metric:
    rows_raw = []
    for user, _, plan in _active_membership_rows(db):
        profile = db.get(FitnessProfile, user.id)
        if profile is None or profile.assigned_trainer_id is None:
            rows_raw.append((user, plan))

    rows = [
        {
            "member": user.full_name,
            "email": user.email,
            "package": plan.name,
            "entitled to programme": "yes" if plan.personalised_programme else "no",
        }
        for user, plan in rows_raw
    ]
    entitled = sum(1 for _, plan in rows_raw if plan.personalised_programme)
    return Metric(
        key="unassigned_members",
        title="Members without a trainer",
        headline=(
            f"{len(rows)} paying members have no trainer assigned; {entitled} of them are on a "
            "package that promises a trainer-written programme."
        ),
        columns=["member", "package", "entitled to programme"],
        rows=rows,
    )


def missing_programmes(db: Session) -> Metric:
    """Members paying for a personalised programme who have not received one."""
    with_programme = set(db.scalars(select(Programme.member_id)).all())
    rows = [
        {"member": user.full_name, "email": user.email, "package": plan.name}
        for user, _, plan in _active_membership_rows(db)
        if plan.personalised_programme and user.id not in with_programme
    ]
    return Metric(
        key="missing_programmes",
        title="Unfulfilled programme promises",
        headline=(
            f"{len(rows)} members pay for a trainer-written programme but do not have one yet."
        ),
        columns=["member", "package"],
        rows=rows,
    )


def idle_members(db: Session) -> Metric:
    cutoff = _midnight(_today() - timedelta(days=IDLE_WINDOW_DAYS))
    recent_bookers = set(
        db.scalars(select(ClassBooking.member_id).where(ClassBooking.created_at >= cutoff)).all()
    )
    rows = [
        {
            "member": user.full_name,
            "email": user.email,
            "package": plan.name,
            "expires": membership.expires_on.strftime("%d %b %Y"),
        }
        for user, membership, plan in _active_membership_rows(db)
        if user.id not in recent_bookers
    ]
    return Metric(
        key="idle_members",
        title="Quiet paying members",
        headline=(
            f"{len(rows)} members with an active package have not booked a class in "
            f"{IDLE_WINDOW_DAYS} days."
        ),
        columns=["member", "package", "expires"],
        rows=rows,
    )


def knowledge_coverage(db: Session) -> Metric:
    documents = db.scalars(select(KnowledgeDocument)).all()
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"documents": 0, "chunks": 0})
    for document in documents:
        grouped[document.discipline]["documents"] += 1
        grouped[document.discipline]["chunks"] += document.chunk_count

    rows = [
        {
            "discipline": discipline,
            "documents": grouped.get(discipline, {}).get("documents", 0),
            "chunks": grouped.get(discipline, {}).get("chunks", 0),
        }
        for discipline in (*DISCIPLINES, "reception")
    ]
    empty = [row["discipline"] for row in rows if row["documents"] == 0]
    return Metric(
        key="knowledge_coverage",
        title="FitBot knowledge base",
        headline=(
            f"{len(documents)} documents ingested."
            + (f" No sources for: {', '.join(empty)}." if empty else " Every discipline covered.")
        ),
        columns=["discipline", "documents", "chunks"],
        rows=rows,
    )


def fitbot_activity(db: Session) -> Metric:
    conversations = db.scalars(select(Conversation)).all()
    total_messages = db.scalar(select(func.count(ChatMessage.id))) or 0
    from_visitors = sum(1 for conversation in conversations if conversation.user_id is None)

    cutoff = _midnight(_today() - timedelta(days=7))
    recent = (
        db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.created_at >= cutoff)) or 0
    )

    rows = [
        {"measure": "conversations", "value": len(conversations)},
        {"measure": "messages", "value": total_messages},
        {"measure": "started by signed-out visitors", "value": from_visitors},
        {"measure": "messages in last 7 days", "value": recent},
    ]
    return Metric(
        key="fitbot_activity",
        title="FitBot usage",
        headline=(
            f"{len(conversations)} conversations and {total_messages} messages so far, "
            f"{from_visitors} started by signed-out visitors."
        ),
        columns=["measure", "value"],
        rows=rows,
    )


# --- Registry -------------------------------------------------------------


@dataclass(frozen=True)
class MetricSpec:
    key: str
    description: str
    run: Callable[[Session], Metric]


REGISTRY: dict[str, MetricSpec] = {
    spec.key: spec
    for spec in [
        MetricSpec(
            "membership_overview",
            (
                "How many members exist, how many hold an active package, lapsed or "
                "never subscribed, split by package."
            ),
            membership_overview,
        ),
        MetricSpec(
            "revenue_summary",
            "Total and recent revenue, and which packages earn the most.",
            revenue_summary,
        ),
        MetricSpec(
            "signup_trend",
            (
                "New member registrations per month over the last six months, and "
                "whether growth is up or down."
            ),
            signup_trend,
        ),
        MetricSpec(
            "expiring_soon",
            "Which memberships expire in the next two weeks and need a renewal call.",
            expiring_soon,
        ),
        MetricSpec(
            "class_utilisation",
            (
                "How full classes are, by discipline: sessions, seats offered, seats "
                "booked and fill rate."
            ),
            class_utilisation,
        ),
        MetricSpec(
            "trainer_load",
            "Workload per trainer: members assigned, programmes written and classes owned.",
            trainer_load,
        ),
        MetricSpec(
            "unassigned_members",
            "Paying members who have no trainer assigned to them.",
            unassigned_members,
        ),
        MetricSpec(
            "missing_programmes",
            "Members who pay for a trainer-written programme but have not been given one.",
            missing_programmes,
        ),
        MetricSpec(
            "idle_members",
            "Members with an active package who have stopped booking classes, a churn warning.",
            idle_members,
        ),
        MetricSpec(
            "knowledge_coverage",
            "Which disciplines have documents in FitBot's knowledge base and which have none.",
            knowledge_coverage,
        ),
        MetricSpec(
            "fitbot_activity",
            "How much FitBot is being used: conversations, messages and visitor traffic.",
            fitbot_activity,
        ),
    ]
}


def catalogue() -> str:
    return "\n".join(f"- {spec.key}: {spec.description}" for spec in REGISTRY.values())


def run_metrics(db: Session, keys: list[str]) -> list[Metric]:
    """Only keys present in the registry are ever executed."""
    return [REGISTRY[key].run(db) for key in keys if key in REGISTRY]


def run_all(db: Session) -> dict[str, Metric]:
    return {key: spec.run(db) for key, spec in REGISTRY.items()}
