from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Discipline = Literal["gym", "yoga", "mma", "reception"]
ProgrammeKind = Literal["workout", "diet"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Authentication -------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    role: str
    full_name: str


class UserResponse(ORMModel):
    id: str
    email: EmailStr
    full_name: str
    phone: str | None = None
    role: str
    active: bool


# --- Packages -------------------------------------------------------------


class PlanResponse(ORMModel):
    id: str
    name: str
    tier: str
    duration_days: int
    price_paise: int
    description: str
    allowed_disciplines: str
    monthly_class_quota: int
    personalised_programme: bool
    priority_support: bool
    active: bool


class PlanWriteRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    tier: str = Field(min_length=2, max_length=30)
    duration_days: int = Field(ge=1, le=1095)
    price_paise: int = Field(ge=0)
    description: str = Field(min_length=2, max_length=1000)
    allowed_disciplines: str = Field(default="gym", max_length=120)
    monthly_class_quota: int = Field(default=0, ge=-1, le=200)
    personalised_programme: bool = False
    priority_support: bool = False
    active: bool = True


class EntitlementsResponse(BaseModel):
    has_active_membership: bool
    plan_name: str | None
    tier: str | None
    expires_on: date | None
    days_remaining: int | None
    allowed_disciplines: list[str]
    monthly_class_quota: int
    classes_booked_this_month: int
    personalised_programme: bool
    priority_support: bool


class MembershipPurchaseRequest(BaseModel):
    plan_id: str


class MembershipResponse(BaseModel):
    membership_id: str
    plan_name: str
    starts_on: date
    expires_on: date
    status: str
    message: str


# --- People ---------------------------------------------------------------


class MemberCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=20)
    role: Literal["member", "trainer"] = "member"


class MemberUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    active: bool | None = None


class RoleChangeRequest(BaseModel):
    role: Literal["member", "trainer", "admin"]


class PersonSummary(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    phone: str | None
    role: str
    active: bool
    plan_name: str | None = None
    expires_on: date | None = None


class ProfileUpdate(BaseModel):
    goal: str | None = Field(default=None, max_length=120)
    experience_level: str | None = Field(default=None, max_length=50)
    injuries_or_limits: str | None = Field(default=None, max_length=1000)
    preferred_domains: str | None = Field(default=None, max_length=120)
    equipment_access: str | None = Field(default=None, max_length=255)


class ProfileResponse(ORMModel):
    goal: str | None
    experience_level: str | None
    injuries_or_limits: str | None
    preferred_domains: str | None
    equipment_access: str | None
    assigned_trainer_id: str | None


# --- Programmes -----------------------------------------------------------


class ProgrammeCreateRequest(BaseModel):
    member_id: str
    kind: ProgrammeKind
    title: str = Field(min_length=2, max_length=150)
    content: str = Field(min_length=2, max_length=20000)


class ProgrammeResponse(ORMModel):
    id: str
    member_id: str
    trainer_id: str
    kind: str
    title: str
    content: str
    active: bool
    created_at: datetime


# --- Classes --------------------------------------------------------------


class ClassCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    discipline: Literal["gym", "yoga", "mma"]
    instructor: str = Field(min_length=2, max_length=120)
    starts_at: datetime
    capacity: int = Field(default=20, ge=1, le=200)


class ClassResponse(BaseModel):
    id: str
    name: str
    discipline: str
    instructor: str
    starts_at: datetime
    capacity: int
    seats_taken: int
    seats_left: int
    booked_by_me: bool


class BookingResponse(BaseModel):
    booking_id: str
    class_name: str
    starts_at: datetime
    message: str


# --- FitBot ---------------------------------------------------------------


class SourceCitation(BaseModel):
    source: str
    page: int | None = None
    excerpt: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    language: str = "en"


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    route: str
    sources: list[SourceCitation] = []
    needs_human_handoff: bool = False
    action: Literal["none", "login", "signup", "show_plans", "upgrade"] = "none"


# --- Admin intelligence ---------------------------------------------------


class MetricTable(BaseModel):
    key: str
    title: str
    headline: str
    columns: list[str]
    rows: list[dict]


class AnalystQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AnalystAnswer(BaseModel):
    question: str
    answer: str
    metrics: list[MetricTable]


class RecommendationItem(BaseModel):
    priority: Literal["high", "medium", "low"]
    category: str
    title: str
    evidence: str
    action: str
    impact: str


class AdvisorReport(BaseModel):
    summary: str
    briefing: str
    recommendations: list[RecommendationItem]


# --- Knowledge base -------------------------------------------------------


class DocumentResponse(ORMModel):
    id: str
    filename: str
    discipline: str
    chunk_count: int
    created_at: datetime
