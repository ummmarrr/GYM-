"""Create the first admin and, optionally, demo data.

Run from the backend folder:
    python -m scripts.seed --admin-email you@example.com --admin-password "your-password"
    python -m scripts.seed --admin-email you@example.com --admin-password "..." --demo
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


def seed_demo(db, admin: User) -> None:
    trainer = upsert_user(db, "trainer@example.com", "Riya Sharma", "TrainerPass123", Role.TRAINER)
    member = upsert_user(db, "member@example.com", "Arjun Patel", "MemberPass123", Role.MEMBER)

    profile = db.get(FitnessProfile, member.id)
    if profile is None:
        profile = FitnessProfile(user_id=member.id)
        db.add(profile)
    profile.goal = "Fat loss and general conditioning"
    profile.experience_level = "beginner"
    profile.equipment_access = "Full commercial gym"
    profile.assigned_trainer_id = trainer.id

    plan = db.query(MembershipPlan).filter(MembershipPlan.tier == "performance").first()
    if plan and not db.query(Membership).filter(Membership.user_id == member.id).first():
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
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--admin-name", default="Master GYM Admin")
    parser.add_argument(
        "--demo", action="store_true", help="Also create a demo trainer, member and classes."
    )
    args = parser.parse_args()

    if len(args.admin_password) < 8:
        print("Admin password must be at least 8 characters.", file=sys.stderr)
        return 1

    initialize_database()
    with SessionLocal() as db:
        print("Seeding Master GYM...")
        admin = upsert_user(db, args.admin_email, args.admin_name, args.admin_password, Role.ADMIN)
        if args.demo:
            seed_demo(db, admin)
        db.commit()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
