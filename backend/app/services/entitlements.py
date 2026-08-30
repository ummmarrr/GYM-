"""Package entitlements.

Tier is the revenue lever, so what a member may do is decided here on the server and
never inferred from the UI or from what FitBot feels like offering.
"""

from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import (
    UNLIMITED_CLASS_QUOTA,
    ClassBooking,
    ClassSchedule,
    Membership,
    MembershipPlan,
    Role,
    User,
)


@dataclass(frozen=True)
class Entitlements:
    has_active_membership: bool
    plan_name: str | None
    tier: str | None
    expires_on: date | None
    allowed_disciplines: tuple[str, ...]
    monthly_class_quota: int
    classes_booked_this_month: int
    personalised_programme: bool
    priority_support: bool

    @property
    def days_remaining(self) -> int | None:
        return (self.expires_on - date.today()).days if self.expires_on else None

    @property
    def can_book_classes(self) -> bool:
        if self.monthly_class_quota == UNLIMITED_CLASS_QUOTA:
            return True
        return self.classes_booked_this_month < self.monthly_class_quota

    def may_book(self, discipline: str) -> tuple[bool, str]:
        """Return whether a booking is allowed, plus a member-facing reason when not."""
        if not self.has_active_membership:
            return False, "You need an active membership to book classes."
        if discipline not in self.allowed_disciplines:
            return False, (
                f"Your {self.plan_name} package does not include {discipline} classes. "
                "Upgrade to unlock them."
            )
        if not self.can_book_classes:
            return False, (
                f"You have used all {self.monthly_class_quota} class bookings included in "
                f"{self.plan_name} this month."
            )
        return True, ""


STAFF_ENTITLEMENTS = Entitlements(
    has_active_membership=True,
    plan_name="Staff",
    tier="staff",
    expires_on=None,
    allowed_disciplines=("gym", "yoga", "mma", "reception"),
    monthly_class_quota=UNLIMITED_CLASS_QUOTA,
    classes_booked_this_month=0,
    personalised_programme=True,
    priority_support=True,
)

NO_MEMBERSHIP = Entitlements(
    has_active_membership=False,
    plan_name=None,
    tier=None,
    expires_on=None,
    allowed_disciplines=(),
    monthly_class_quota=0,
    classes_booked_this_month=0,
    personalised_programme=False,
    priority_support=False,
)


def active_membership(db: Session, user_id: str) -> Membership | None:
    return db.scalars(
        select(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.status == "active",
            Membership.expires_on >= date.today(),
        )
        .order_by(Membership.expires_on.desc())
    ).first()


def _bookings_this_month(db: Session, user_id: str) -> int:
    first_of_month = datetime.combine(date.today().replace(day=1), time.min)
    return len(
        db.scalars(
            select(ClassBooking)
            .join(ClassSchedule, ClassSchedule.id == ClassBooking.class_id)
            .where(ClassBooking.member_id == user_id, ClassSchedule.starts_at >= first_of_month)
        ).all()
    )


def entitlements_for(db: Session, user: User) -> Entitlements:
    if user.role in (Role.ADMIN, Role.TRAINER):
        return STAFF_ENTITLEMENTS

    # Reception may identify and check in members, but it intentionally receives none of
    # the trainer/admin membership bypasses.
    if user.role is Role.RECEPTION:
        return NO_MEMBERSHIP

    membership = active_membership(db, user.id)
    if membership is None:
        return NO_MEMBERSHIP

    plan: MembershipPlan = membership.plan
    return Entitlements(
        has_active_membership=True,
        plan_name=plan.name,
        tier=plan.tier,
        expires_on=membership.expires_on,
        allowed_disciplines=tuple(
            d.strip() for d in plan.allowed_disciplines.split(",") if d.strip()
        ),
        monthly_class_quota=plan.monthly_class_quota,
        classes_booked_this_month=_bookings_this_month(db, user.id),
        personalised_programme=plan.personalised_programme,
        priority_support=plan.priority_support,
    )
