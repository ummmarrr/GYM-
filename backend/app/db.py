from datetime import UTC, date, datetime
from enum import Enum
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.core.config import get_settings


def utc_now() -> datetime:
    """Return naive UTC, because SQLite columns here are timezone-naive."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    MEMBER = "member"
    TRAINER = "trainer"
    ADMIN = "admin"


class Discipline(str, Enum):
    GYM = "gym"
    YOGA = "yoga"
    MMA = "mma"
    RECEPTION = "reception"


UNLIMITED_CLASS_QUOTA = -1


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(SqlEnum(Role), default=Role.MEMBER)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # FitnessProfile points at users twice (the member and their trainer), so the join
    # column has to be named explicitly.
    profile: Mapped["FitnessProfile | None"] = relationship(
        back_populates="user", foreign_keys="FitnessProfile.user_id"
    )


class MembershipPlan(Base):
    """A sellable package. The entitlement columns are what the tier actually unlocks."""

    __tablename__ = "membership_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True)
    tier: Mapped[str] = mapped_column(String(30))
    duration_days: Mapped[int]
    price_paise: Mapped[int]
    description: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)

    allowed_disciplines: Mapped[str] = mapped_column(String(120), default="gym")
    monthly_class_quota: Mapped[int] = mapped_column(default=0)
    personalised_programme: Mapped[bool] = mapped_column(default=False)
    priority_support: Mapped[bool] = mapped_column(default=False)


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("membership_plans.id"))
    starts_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    plan: Mapped[MembershipPlan] = relationship()


class FitnessProfile(Base):
    __tablename__ = "fitness_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    goal: Mapped[str | None] = mapped_column(String(120))
    experience_level: Mapped[str | None] = mapped_column(String(50))
    injuries_or_limits: Mapped[str | None] = mapped_column(Text)
    preferred_domains: Mapped[str | None] = mapped_column(String(120))
    equipment_access: Mapped[str | None] = mapped_column(String(255))
    assigned_trainer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    user: Mapped[User] = relationship(back_populates="profile", foreign_keys=[user_id])


class Programme(Base):
    """A workout or diet plan a trainer assigns to one member."""

    __tablename__ = "programmes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    member_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    trainer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(150))
    content: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ClassSchedule(Base):
    __tablename__ = "class_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    discipline: Mapped[str] = mapped_column(String(50))
    instructor: Mapped[str] = mapped_column(String(120))
    trainer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    capacity: Mapped[int] = mapped_column(default=20)


class ClassBooking(Base):
    __tablename__ = "class_bookings"
    __table_args__ = (UniqueConstraint("class_id", "member_id", name="uq_booking_once"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    class_id: Mapped[str] = mapped_column(ForeignKey("class_schedules.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    filename: Mapped[str] = mapped_column(String(255))
    discipline: Mapped[str] = mapped_column(String(50))
    document_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    chunk_count: Mapped[int] = mapped_column(default=0)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class KnowledgeChunk(Base):
    """One passage of an approved PDF, with the embedding used to find it.

    Vectors live beside the documents they describe so a search can filter by discipline and
    rank by similarity in a single query.
    """

    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_hash: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(255))
    page: Mapped[int | None] = mapped_column()
    discipline: Mapped[str] = mapped_column(String(50), index=True)
    content: Mapped[str] = mapped_column(Text)
    parent_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SQLite has no vector type. The tests run there and stub retrieval out; search itself
    # requires Postgres.
    embedding: Mapped[list[float]] = mapped_column(
        Vector(get_settings().embedding_dimensions).with_variant(Text, "sqlite")
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


settings = get_settings()
is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
# Neon suspends an idle compute and its pooler drops connections, so a pooled connection can
# be dead by the time it is reused. Check it before handing it out.
pool_args = {} if is_sqlite else {"pool_pre_ping": True, "pool_recycle": 300}
engine = create_engine(settings.database_url, connect_args=connect_args, **pool_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def default_plans() -> list[MembershipPlan]:
    """Fresh instances each call, because ORM objects cannot be shared across sessions."""
    return [
        MembershipPlan(
            name="Starter",
            tier="starter",
            duration_days=30,
            price_paise=149900,
            description="Full gym floor access with FitBot for general fitness questions.",
            allowed_disciplines="gym",
            monthly_class_quota=0,
            personalised_programme=False,
            priority_support=False,
        ),
        MembershipPlan(
            name="Performance",
            tier="performance",
            duration_days=90,
            price_paise=399900,
            description="Gym access, a trainer-assigned programme, and up to 8 classes a month.",
            allowed_disciplines="gym,yoga",
            monthly_class_quota=8,
            personalised_programme=True,
            priority_support=False,
        ),
        MembershipPlan(
            name="Complete",
            tier="complete",
            duration_days=180,
            price_paise=699900,
            description="Everything in Performance plus unlimited Yoga and MMA classes.",
            allowed_disciplines="gym,yoga,mma",
            monthly_class_quota=UNLIMITED_CLASS_QUOTA,
            personalised_programme=True,
            priority_support=True,
        ),
    ]


def initialize_database() -> None:
    if not is_sqlite:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(engine)

    if not is_sqlite:
        # Approximate-nearest-neighbour index. Postgres falls back to an exact scan without
        # it, which is fine for a few hundred chunks and slow for a few hundred thousand.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding "
                    "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
                )
            )

    with SessionLocal() as db:
        if db.query(MembershipPlan).count() == 0:
            db.add_all(default_plans())
            db.commit()
