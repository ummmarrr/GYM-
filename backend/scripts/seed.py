"""Create the first admin and, optionally, demo data.

Run from the backend folder:
    python -m scripts.seed --admin-email you@example.com --admin-password "your-password"
    python -m scripts.seed --admin-email you@example.com --admin-password "..." --demo
    python -m scripts.seed --public-demo
"""

import argparse
import sys
from datetime import date, timedelta

from app.core.security import hash_password
from app.db import (
    ClassSchedule,
    FitnessProfile,
    Membership,
    MembershipPlan,
    Programme,
    Role,
    SessionLocal,
    User,
    initialize_database,
    utc_now,
)


def upsert_user(db, email: str, full_name: str, password: str, role: Role) -> User:
    email = email.lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
        )
        db.add(user)
        db.flush()
        print(f"  created {role.value}: {email}")
    else:
        user.role = role
        user.password_hash = hash_password(password)
        user.active = True
        print(f"  updated {role.value}: {email}")
    return user


def attach_profile(db, member: User, trainer: User) -> None:
    profile = db.get(FitnessProfile, member.id)
    if profile is None:
        profile = FitnessProfile(user_id=member.id)
        db.add(profile)
    profile.goal = "Fat loss and general conditioning"
    profile.experience_level = "beginner"
    profile.equipment_access = "Full commercial gym"
    profile.assigned_trainer_id = trainer.id


def give_membership(db, member: User, tier: str = "performance") -> None:
    plan = db.query(MembershipPlan).filter(MembershipPlan.tier == tier).first()
    if plan is None or db.query(Membership).filter(Membership.user_id == member.id).first():
        return
    starts_on = date.today()
    db.add(
        Membership(
            user_id=member.id,
            plan_id=plan.id,
            starts_on=starts_on,
            expires_on=starts_on + timedelta(days=plan.duration_days),
        )
    )
    print(f"  gave {member.email} the {plan.name} package")


def seed_public_demo(db) -> None:
    """The three logins printed on the sign-in page.

    Their passwords are public, so the API refuses writes from these addresses; see
    Settings.demo_account_emails. Keep the emails in step with that setting.
    """
    upsert_user(db, "admin-demo@example.com", "Demo Admin", "DemoAdmin123", Role.ADMIN)
    trainer = upsert_user(
        db, "trainer-demo@example.com", "Demo Trainer", "DemoTrainer123", Role.TRAINER
    )
    member = upsert_user(db, "member-demo@example.com", "Demo Member", "DemoMember123", Role.MEMBER)
    attach_profile(db, member, trainer)
    give_membership(db, member)

    # An empty member dashboard is a poor first impression, and the demo trainer cannot
    # write one because the account is read-only.
    if not db.query(Programme).filter(Programme.member_id == member.id).first():
        db.add(
            Programme(
                member_id=member.id,
                trainer_id=trainer.id,
                kind="workout",
                title="Week 1 — full body, three days",
                content=(
                    "Mon: goblet squat 3x8, push-up 3x10, seated row 3x12, plank 3x30s\n"
                    "Wed: 20 min brisk incline walk, hip hinge drill 3x10, dead bug 3x10\n"
                    "Fri: dumbbell bench 3x8, lat pulldown 3x10, split squat 3x8 each side\n"
                    "Rest two minutes between sets. Add weight only once every rep is clean."
                ),
            )
        )
        print(f"  wrote a starter programme for {member.email}")


def seed_demo(db) -> None:
    trainer = upsert_user(db, "trainer@example.com", "Riya Sharma", "TrainerPass123", Role.TRAINER)
    member = upsert_user(db, "member@example.com", "Arjun Patel", "MemberPass123", Role.MEMBER)

    attach_profile(db, member, trainer)
    give_membership(db, member)

    if db.query(ClassSchedule).count() == 0:
        base = utc_now().replace(hour=7, minute=0, second=0, microsecond=0) + timedelta(days=1)
        db.add_all(
            [
                ClassSchedule(
                    name="Morning Strength",
                    discipline="gym",
                    instructor=trainer.full_name,
                    trainer_id=trainer.id,
                    starts_at=base,
                    capacity=15,
                ),
                ClassSchedule(
                    name="Vinyasa Flow",
                    discipline="yoga",
                    instructor=trainer.full_name,
                    trainer_id=trainer.id,
                    starts_at=base + timedelta(days=1, hours=11),
                    capacity=20,
                ),
                ClassSchedule(
                    name="MMA Fundamentals",
                    discipline="mma",
                    instructor=trainer.full_name,
                    trainer_id=trainer.id,
                    starts_at=base + timedelta(days=2, hours=12),
                    capacity=12,
                ),
            ]
        )
        print("  added 3 demo classes")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Master GYM database.")
    parser.add_argument("--admin-email")
    parser.add_argument("--admin-password")
    parser.add_argument("--admin-name", default="Master GYM Admin")
    parser.add_argument(
        "--demo", action="store_true", help="Also create a demo trainer, member and classes."
    )
    parser.add_argument(
        "--public-demo",
        action="store_true",
        help="Create the read-only logins advertised on the sign-in page.",
    )
    args = parser.parse_args()

    wants_admin = bool(args.admin_email or args.admin_password)
    if wants_admin and not (args.admin_email and args.admin_password):
        print("--admin-email and --admin-password go together.", file=sys.stderr)
        return 1
    if not wants_admin and not (args.demo or args.public_demo):
        print("Nothing to do: pass admin credentials, --demo or --public-demo.", file=sys.stderr)
        return 1
    if wants_admin and len(args.admin_password) < 8:
        print("Admin password must be at least 8 characters.", file=sys.stderr)
        return 1

    initialize_database()
    with SessionLocal() as db:
        print("Seeding Master GYM...")
        if wants_admin:
            upsert_user(db, args.admin_email, args.admin_name, args.admin_password, Role.ADMIN)
        if args.demo:
            seed_demo(db)
        if args.public_demo:
            seed_public_demo(db)
        db.commit()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
