"""Packages, memberships, classes and bookings — the member-facing side of Master GYM."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db import (
    AuditEvent,
    ClassBooking,
    ClassSchedule,
    Membership,
    MembershipPlan,
    Role,
    User,
    get_db,
    utc_now,
)
from app.schemas import (
    BookingResponse,
    ClassCreateRequest,
    ClassResponse,
    EntitlementsResponse,
    MembershipPurchaseRequest,
    MembershipResponse,
    PlanResponse,
    PlanWriteRequest,
)
from app.services.entitlements import entitlements_for

router = APIRouter(tags=["membership"])


def entitlements_payload(db: Session, user: User) -> EntitlementsResponse:
    ent = entitlements_for(db, user)
    return EntitlementsResponse(
        has_active_membership=ent.has_active_membership,
        plan_name=ent.plan_name,
        tier=ent.tier,
        expires_on=ent.expires_on,
        days_remaining=ent.days_remaining,
        allowed_disciplines=list(ent.allowed_disciplines),
        monthly_class_quota=ent.monthly_class_quota,
        classes_booked_this_month=ent.classes_booked_this_month,
        personalised_programme=ent.personalised_programme,
        priority_support=ent.priority_support,
    )


@router.get("/plans", response_model=list[PlanResponse])
def list_plans(db: Annotated[Session, Depends(get_db)]):
    """Public: the pricing page needs this before anyone signs in."""
    return db.scalars(
        select(MembershipPlan)
        .where(MembershipPlan.active.is_(True))
        .order_by(MembershipPlan.price_paise)
    ).all()


@router.post("/admin/plans", response_model=PlanResponse, status_code=201)
def create_plan(
    payload: PlanWriteRequest,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    if db.query(MembershipPlan).filter(MembershipPlan.name == payload.name).first():
        raise HTTPException(status_code=409, detail="A package with this name already exists.")
    plan = MembershipPlan(**payload.model_dump())
    db.add(plan)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="plan.created",
            resource_type="membership_plan",
            resource_id=plan.id,
            detail=plan.name,
        )
    )
    db.commit()
    return plan


@router.put("/admin/plans/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: str,
    payload: PlanWriteRequest,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    plan = db.get(MembershipPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Package not found.")
    for field, value in payload.model_dump().items():
        setattr(plan, field, value)
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="plan.updated",
            resource_type="membership_plan",
            resource_id=plan.id,
            detail=plan.name,
        )
    )
    db.commit()
    return plan


@router.get("/me/entitlements", response_model=EntitlementsResponse)
def my_entitlements(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return entitlements_payload(db, current_user)


@router.post("/me/membership", response_model=MembershipResponse, status_code=201)
def purchase_membership(
    payload: MembershipPurchaseRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Simulated checkout. Swap this for a payment provider callback before going live."""
    plan = db.get(MembershipPlan, payload.plan_id)
    if plan is None or not plan.active:
        raise HTTPException(status_code=404, detail="Package not found.")

    starts_on = date.today()
    membership = Membership(
        user_id=current_user.id,
        plan_id=plan.id,
        starts_on=starts_on,
        expires_on=starts_on + timedelta(days=plan.duration_days),
        status="active",
    )
    db.add(membership)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="membership.activated",
            resource_type="membership",
            resource_id=membership.id,
            detail=f"{plan.name} (simulated payment)",
        )
    )
    db.commit()
    return MembershipResponse(
        membership_id=membership.id,
        plan_name=plan.name,
        starts_on=membership.starts_on,
        expires_on=membership.expires_on,
        status=membership.status,
        message=(
            f"{plan.name} is active until {membership.expires_on:%d %b %Y}. Payment was simulated."
        ),
    )


def _seat_counts(db: Session) -> dict[str, int]:
    return dict(
        db.execute(
            select(ClassBooking.class_id, func.count(ClassBooking.id)).group_by(
                ClassBooking.class_id
            )
        ).all()
    )


@router.get("/classes", response_model=list[ClassResponse])
def list_classes(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    classes = db.scalars(
        select(ClassSchedule)
        .where(ClassSchedule.starts_at >= utc_now())
        .order_by(ClassSchedule.starts_at)
    ).all()
    taken = _seat_counts(db)
    mine = {
        booking.class_id
        for booking in db.scalars(
            select(ClassBooking).where(ClassBooking.member_id == current_user.id)
        ).all()
    }
    return [
        ClassResponse(
            id=item.id,
            name=item.name,
            discipline=item.discipline,
            instructor=item.instructor,
            starts_at=item.starts_at,
            capacity=item.capacity,
            seats_taken=taken.get(item.id, 0),
            seats_left=max(item.capacity - taken.get(item.id, 0), 0),
            booked_by_me=item.id in mine,
        )
        for item in classes
    ]


@router.post("/classes/{class_id}/book", response_model=BookingResponse, status_code=201)
def book_class(
    class_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    session = db.get(ClassSchedule, class_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Class not found.")

    allowed, reason = entitlements_for(db, current_user).may_book(session.discipline)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)

    already = db.scalars(
        select(ClassBooking).where(
            ClassBooking.class_id == class_id, ClassBooking.member_id == current_user.id
        )
    ).first()
    if already:
        raise HTTPException(status_code=409, detail="You have already booked this class.")

    seats_taken = _seat_counts(db).get(class_id, 0)
    if seats_taken >= session.capacity:
        raise HTTPException(status_code=409, detail="This class is full.")

    booking = ClassBooking(class_id=class_id, member_id=current_user.id)
    db.add(booking)
    db.flush()
    db.commit()
    return BookingResponse(
        booking_id=booking.id,
        class_name=session.name,
        starts_at=session.starts_at,
        message=f"Booked. See you at {session.name} on {session.starts_at:%d %b, %I:%M %p}.",
    )


@router.delete("/classes/{class_id}/book", status_code=200)
def cancel_booking(
    class_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    booking = db.scalars(
        select(ClassBooking).where(
            ClassBooking.class_id == class_id, ClassBooking.member_id == current_user.id
        )
    ).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="You have not booked this class.")
    db.delete(booking)
    db.commit()
    return {"message": "Booking cancelled."}


@router.post("/staff/classes", status_code=201)
def create_class(
    payload: ClassCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.role not in (Role.ADMIN, Role.TRAINER):
        raise HTTPException(status_code=403, detail="Only staff can create classes.")
    session = ClassSchedule(**payload.model_dump(), trainer_id=current_user.id)
    db.add(session)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="class.created",
            resource_type="class_schedule",
            resource_id=session.id,
            detail=session.name,
        )
    )
    db.commit()
    return {"id": session.id, "message": "Class added to the schedule."}


@router.delete("/staff/classes/{class_id}", status_code=200)
def delete_class(
    class_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.role not in (Role.ADMIN, Role.TRAINER):
        raise HTTPException(status_code=403, detail="Only staff can remove classes.")
    session = db.get(ClassSchedule, class_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Class not found.")
    if current_user.role is Role.TRAINER and session.trainer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Trainers can only remove their own classes.")

    for booking in db.scalars(select(ClassBooking).where(ClassBooking.class_id == class_id)).all():
        db.delete(booking)
    db.delete(session)
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="class.deleted",
            resource_type="class_schedule",
            resource_id=class_id,
            detail=session.name,
        )
    )
    db.commit()
    return {"message": "Class removed."}
