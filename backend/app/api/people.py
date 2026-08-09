"""Member and trainer management, fitness profiles, and assigned programmes."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, require_staff
from app.core.security import hash_password
from app.db import (
    AuditEvent,
    ClassBooking,
    FitnessProfile,
    Membership,
    MembershipPlan,
    Programme,
    Role,
    User,
    get_db,
)
from app.schemas import (
    MemberCreateRequest,
    MemberUpdateRequest,
    PersonSummary,
    ProfileResponse,
    ProfileUpdate,
    ProgrammeCreateRequest,
    ProgrammeResponse,
    RoleChangeRequest,
)
from app.services.entitlements import active_membership

router = APIRouter(tags=["people"])


def _summary(db: Session, user: User) -> PersonSummary:
    membership = active_membership(db, user.id) if user.role is Role.MEMBER else None
    return PersonSummary(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        role=user.role.value,
        active=user.active,
        plan_name=membership.plan.name if membership else None,
        expires_on=membership.expires_on if membership else None,
    )


def _profile_for(db: Session, user_id: str) -> FitnessProfile:
    profile = db.get(FitnessProfile, user_id)
    if profile is None:
        profile = FitnessProfile(user_id=user_id)
        db.add(profile)
        db.flush()
    return profile


# --- Admin ----------------------------------------------------------------


@router.get("/admin/people", response_model=list[PersonSummary])
def list_people(
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[str | None, Query()] = None,
):
    statement = select(User).order_by(User.created_at.desc())
    if role:
        statement = statement.where(User.role == Role(role))
    return [_summary(db, user) for user in db.scalars(statement).all()]


@router.post("/admin/people", response_model=PersonSummary, status_code=201)
def create_person(
    payload: MemberCreateRequest,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    email = str(payload.email).lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=Role(payload.role),
    )
    db.add(user)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="person.created",
            resource_type="user",
            resource_id=user.id,
            detail=f"{email} as {payload.role}",
        )
    )
    db.commit()
    return _summary(db, user)


@router.patch("/admin/people/{user_id}", response_model=PersonSummary)
def update_person(
    user_id: str,
    payload: MemberUpdateRequest,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    if user.id == current_user.id and payload.active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="person.updated",
            resource_type="user",
            resource_id=user.id,
            detail=user.email,
        )
    )
    db.commit()
    return _summary(db, user)


@router.post("/admin/people/{user_id}/role", response_model=PersonSummary)
def change_role(
    user_id: str,
    payload: RoleChangeRequest,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role.")

    previous = user.role.value
    user.role = Role(payload.role)
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="person.role_changed",
            resource_type="user",
            resource_id=user.id,
            detail=f"{previous} -> {payload.role}",
        )
    )
    db.commit()
    return _summary(db, user)


@router.post("/admin/people/{member_id}/trainer/{trainer_id}", response_model=ProfileResponse)
def assign_trainer(
    member_id: str,
    trainer_id: str,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    member = db.get(User, member_id)
    trainer = db.get(User, trainer_id)
    if member is None or member.role is not Role.MEMBER:
        raise HTTPException(status_code=404, detail="Member not found.")
    if trainer is None or trainer.role is not Role.TRAINER:
        raise HTTPException(status_code=404, detail="Trainer not found.")

    profile = _profile_for(db, member_id)
    profile.assigned_trainer_id = trainer_id
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="member.trainer_assigned",
            resource_type="user",
            resource_id=member_id,
            detail=trainer.email,
        )
    )
    db.commit()
    return profile


@router.get("/admin/overview")
def admin_overview(
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    counts = dict(db.execute(select(User.role, func.count(User.id)).group_by(User.role)).all())
    active_memberships = db.scalar(
        select(func.count(Membership.id)).where(
            Membership.status == "active", Membership.expires_on >= date.today()
        )
    )
    revenue_paise = db.scalar(
        select(func.coalesce(func.sum(MembershipPlan.price_paise), 0))
        .select_from(Membership)
        .join(MembershipPlan, MembershipPlan.id == Membership.plan_id)
    )
    return {
        "members": counts.get(Role.MEMBER, 0),
        "trainers": counts.get(Role.TRAINER, 0),
        "admins": counts.get(Role.ADMIN, 0),
        "active_memberships": active_memberships or 0,
        "memberships_sold": db.scalar(select(func.count(Membership.id))) or 0,
        "revenue_paise": revenue_paise or 0,
        "class_bookings": db.scalar(select(func.count(ClassBooking.id))) or 0,
    }


# --- Trainer --------------------------------------------------------------


@router.get("/trainer/members", response_model=list[PersonSummary])
def my_members(
    current_user: Annotated[User, Depends(require_staff)],
    db: Annotated[Session, Depends(get_db)],
):
    """Admins see everyone; trainers see only the members assigned to them."""
    if current_user.role is Role.ADMIN:
        statement = select(User).where(User.role == Role.MEMBER)
    else:
        statement = (
            select(User)
            .join(FitnessProfile, FitnessProfile.user_id == User.id)
            .where(FitnessProfile.assigned_trainer_id == current_user.id)
        )
    return [_summary(db, user) for user in db.scalars(statement).all()]


@router.post("/staff/programmes", response_model=ProgrammeResponse, status_code=201)
def create_programme(
    payload: ProgrammeCreateRequest,
    current_user: Annotated[User, Depends(require_staff)],
    db: Annotated[Session, Depends(get_db)],
):
    member = db.get(User, payload.member_id)
    if member is None or member.role is not Role.MEMBER:
        raise HTTPException(status_code=404, detail="Member not found.")

    if current_user.role is Role.TRAINER:
        profile = db.get(FitnessProfile, member.id)
        if profile is None or profile.assigned_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="This member is not assigned to you.")

    programme = Programme(
        member_id=payload.member_id,
        trainer_id=current_user.id,
        kind=payload.kind,
        title=payload.title,
        content=payload.content,
    )
    db.add(programme)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="programme.created",
            resource_type="programme",
            resource_id=programme.id,
            detail=f"{payload.kind} for {member.email}",
        )
    )
    db.commit()
    return programme


@router.get("/staff/members/{member_id}/programmes", response_model=list[ProgrammeResponse])
def member_programmes(
    member_id: str,
    current_user: Annotated[User, Depends(require_staff)],
    db: Annotated[Session, Depends(get_db)],
):
    if current_user.role is Role.TRAINER:
        profile = db.get(FitnessProfile, member_id)
        if profile is None or profile.assigned_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="This member is not assigned to you.")
    return db.scalars(
        select(Programme)
        .where(Programme.member_id == member_id)
        .order_by(Programme.created_at.desc())
    ).all()


# --- Every signed-in user -------------------------------------------------


@router.get("/me/profile", response_model=ProfileResponse)
def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    profile = _profile_for(db, current_user.id)
    db.commit()
    return profile


@router.put("/me/profile", response_model=ProfileResponse)
def update_my_profile(
    payload: ProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    profile = _profile_for(db, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    return profile


@router.get("/me/programmes", response_model=list[ProgrammeResponse])
def my_programmes(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(
        select(Programme)
        .where(Programme.member_id == current_user.id, Programme.active.is_(True))
        .order_by(Programme.created_at.desc())
    ).all()
