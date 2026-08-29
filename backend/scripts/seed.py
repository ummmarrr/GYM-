"""Create the first admin and, optionally, demo data.

Run from the backend folder:
    python -m scripts.seed --admin-email you@example.com --admin-password "your-password"
    python -m scripts.seed --admin-email you@example.com --admin-password "..." --demo
    python -m scripts.seed --public-demo
    python -m scripts.seed --rich-demo
"""

import argparse
import sys
from datetime import date, timedelta

from app.core.security import hash_password
from app.db import (
    ClassBooking,
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


def _plan_by_tier(db, tier: str) -> MembershipPlan | None:
    return db.query(MembershipPlan).filter(MembershipPlan.tier == tier).first()


def _grant_membership(
    db, member: User, tier: str, *, days_ago_started: int = 0, expired: bool = False
) -> Membership | None:
    """Give a member a package, backdated or already expired, so renewal/lapsed views have data."""
    plan = _plan_by_tier(db, tier)
    if plan is None:
        return None
    existing = db.query(Membership).filter(Membership.user_id == member.id).first()
    if existing:
        return existing
    starts_on = date.today() - timedelta(days=days_ago_started)
    expires_on = (
        date.today() - timedelta(days=1)
        if expired
        else starts_on + timedelta(days=plan.duration_days)
    )
    membership = Membership(
        user_id=member.id,
        plan_id=plan.id,
        starts_on=starts_on,
        expires_on=expires_on,
        status="active" if not expired else "expired",
    )
    db.add(membership)
    db.flush()
    print(f"  gave {member.email} the {plan.name} package (expires {expires_on})")
    return membership


def _set_profile(
    db,
    member: User,
    trainer: User | None,
    *,
    goal: str,
    experience: str,
    injuries: str | None = None,
    equipment: str = "Full commercial gym",
) -> None:
    profile = db.get(FitnessProfile, member.id)
    if profile is None:
        profile = FitnessProfile(user_id=member.id)
        db.add(profile)
    profile.goal = goal
    profile.experience_level = experience
    profile.injuries_or_limits = injuries
    profile.equipment_access = equipment
    profile.assigned_trainer_id = trainer.id if trainer else None


def _add_programme(db, member: User, trainer: User, kind: str, title: str, content: str) -> None:
    if db.query(Programme).filter(
        Programme.member_id == member.id, Programme.kind == kind
    ).first():
        return
    db.add(
        Programme(
            member_id=member.id,
            trainer_id=trainer.id,
            kind=kind,
            title=title,
            content=content,
        )
    )
    print(f"  wrote a {kind} programme for {member.email}")


def _book(db, member: User, session: ClassSchedule) -> None:
    already = (
        db.query(ClassBooking)
        .filter(ClassBooking.class_id == session.id, ClassBooking.member_id == member.id)
        .first()
    )
    if already:
        return
    db.add(ClassBooking(class_id=session.id, member_id=member.id))


def seed_rich_demo(db) -> None:
    """A realistic-sized dataset: 3 trainers, 8 members across every package, a full week
    of classes at varied fill levels, bookings, and programmes — enough to exercise FitBot,
    entitlements, the analyst/advisor agents and the Copilot with real numbers instead of
    an almost-empty database.
    """
    print("Seeding rich demo dataset...")

    # --- Trainers -----------------------------------------------------
    riya = upsert_user(db, "riya.trainer@example.com", "Riya Sharma", "TrainerPass123", Role.TRAINER)
    karan = upsert_user(db, "karan.trainer@example.com", "Karan Verma", "TrainerPass123", Role.TRAINER)
    # Neha is deliberately idle (no members, no classes) so trainer-load imbalance shows up.
    upsert_user(db, "neha.trainer@example.com", "Neha Singh", "TrainerPass123", Role.TRAINER)

    # --- Members, one per interesting scenario -------------------------
    arjun = upsert_user(db, "arjun.member@example.com", "Arjun Patel", "MemberPass123", Role.MEMBER)
    priya = upsert_user(db, "priya.member@example.com", "Priya Nair", "MemberPass123", Role.MEMBER)
    rahul = upsert_user(db, "rahul.member@example.com", "Rahul Gupta", "MemberPass123", Role.MEMBER)
    sara = upsert_user(db, "sara.member@example.com", "Sara Khan", "MemberPass123", Role.MEMBER)
    vikram = upsert_user(db, "vikram.member@example.com", "Vikram Rao", "MemberPass123", Role.MEMBER)
    ananya = upsert_user(db, "ananya.member@example.com", "Ananya Iyer", "MemberPass123", Role.MEMBER)
    dev = upsert_user(db, "dev.member@example.com", "Dev Malhotra", "MemberPass123", Role.MEMBER)
    lisa = upsert_user(db, "lisa.member@example.com", "Lisa Fernandes", "MemberPass123", Role.MEMBER)

    # Packages: cover Starter / Performance / Complete, plus a lapsed and a never-subscribed member.
    _grant_membership(db, arjun, "complete", days_ago_started=40)
    _grant_membership(db, priya, "performance", days_ago_started=10)
    _grant_membership(db, rahul, "starter", days_ago_started=5)
    _grant_membership(db, sara, "performance", days_ago_started=85)  # expires soon
    _grant_membership(db, vikram, "complete", days_ago_started=20)
    _grant_membership(db, ananya, "starter", days_ago_started=60, expired=True)  # lapsed
    _grant_membership(db, dev, "performance", days_ago_started=3)
    # lisa: intentionally no membership yet, so "never subscribed" has a real row.

    # Fitness profiles + trainer assignment (dev and lisa left unassigned on purpose).
    _set_profile(db, arjun, riya, goal="Build strength", experience="intermediate")
    _set_profile(db, priya, riya, goal="Improve flexibility", experience="beginner")
    _set_profile(db, rahul, karan, goal="Fat loss", experience="beginner")
    _set_profile(
        db, sara, karan, goal="MMA conditioning", experience="intermediate",
        injuries="Old ankle sprain, avoid heavy plyometrics",
    )
    _set_profile(db, vikram, riya, goal="Powerlifting total", experience="advanced")
    _set_profile(db, ananya, None, goal="General fitness", experience="beginner")

    # Programmes: give most Performance/Complete members one, but leave Dev without a
    # programme even though his package promises one — this is what should trigger the
    # "unfulfilled programme promises" recommendation in the AdvisorAgent.
    _add_programme(
        db, arjun, riya, "workout", "Strength block 1 — upper/lower split",
        "Mon: bench 4x6, row 4x8, overhead press 3x8\n"
        "Wed: squat 4x6, RDL 3x8, walking lunge 3x10 each\n"
        "Fri: deadlift 3x5, pull-up 4xAMRAP, plank 3x45s",
    )
    _add_programme(
        db, priya, riya, "workout", "Mobility & light strength — 3 days",
        "Mon: sun salutations x5, goblet squat 3x10, band pull-apart 3x15\n"
        "Wed: hip flexor stretch 3x30s each, glute bridge 3x12, dead bug 3x10\n"
        "Fri: full-body flow 20 min, single-leg RDL 3x8 each side",
    )
    _add_programme(
        db, priya, riya, "diet", "Balanced maintenance plan",
        "Breakfast: oats + fruit + nuts. Lunch: dal, rice, vegetable, curd.\n"
        "Dinner: grilled protein, salad, one roti. Snacks: fruit, roasted chana.",
    )
    _add_programme(
        db, sara, karan, "workout", "MMA conditioning — ankle-safe",
        "Mon: shadow boxing 4x3min, core circuit 3 rounds\n"
        "Wed: pad work with coach, low-impact footwork drills\n"
        "Fri: grappling positional drilling, mobility cooldown",
    )
    _add_programme(
        db, vikram, riya, "workout", "Powerlifting peak block",
        "Mon: squat 5x3 @ 85%, accessory leg work\n"
        "Wed: bench 5x3 @ 85%, triceps + upper back\n"
        "Fri: deadlift 5x3 @ 85%, core work",
    )
    # dev: Performance package promises a programme — deliberately left unwritten.

    # --- Classes across the coming week, at deliberately varied fill levels -----------
    if db.query(ClassSchedule).count() == 0:
        base = utc_now().replace(hour=6, minute=30, second=0, microsecond=0) + timedelta(days=1)
        classes = {
            "gym_mon": ClassSchedule(
                name="Morning Strength", discipline="gym", instructor=riya.full_name,
                trainer_id=riya.id, starts_at=base, capacity=12,
            ),
            "gym_wed": ClassSchedule(
                name="Full Body Conditioning", discipline="gym", instructor=karan.full_name,
                trainer_id=karan.id, starts_at=base + timedelta(days=2, hours=1), capacity=15,
            ),
            "gym_fri": ClassSchedule(
                name="Powerlifting Technique", discipline="gym", instructor=riya.full_name,
                trainer_id=riya.id, starts_at=base + timedelta(days=4, hours=2), capacity=8,
            ),
            "yoga_tue": ClassSchedule(
                name="Vinyasa Flow", discipline="yoga", instructor=riya.full_name,
                trainer_id=riya.id, starts_at=base + timedelta(days=1, hours=5), capacity=20,
            ),
            "yoga_thu": ClassSchedule(
                name="Evening Restorative Yoga", discipline="yoga", instructor=karan.full_name,
                trainer_id=karan.id, starts_at=base + timedelta(days=3, hours=12), capacity=20,
            ),
            "mma_wed": ClassSchedule(
                name="MMA Fundamentals", discipline="mma", instructor=karan.full_name,
                trainer_id=karan.id, starts_at=base + timedelta(days=2, hours=6), capacity=10,
            ),
            "mma_sat": ClassSchedule(
                name="Sparring & Pad Work", discipline="mma", instructor=karan.full_name,
                trainer_id=karan.id, starts_at=base + timedelta(days=5, hours=3), capacity=10,
            ),
        }
        db.add_all(classes.values())
        db.flush()
        print(f"  added {len(classes)} demo classes across the week")

        # Bookings: pack gym_fri near capacity, leave yoga_thu nearly empty, book others
        # moderately — this gives class_utilisation and the timetable-related
        # recommendations something real to report on.
        _book(db, arjun, classes["gym_mon"])
        _book(db, vikram, classes["gym_mon"])
        _book(db, priya, classes["yoga_tue"])
        _book(db, arjun, classes["gym_wed"])
        _book(db, rahul, classes["gym_wed"])
        _book(db, vikram, classes["gym_fri"])
        _book(db, arjun, classes["gym_fri"])
        for extra in (priya, rahul, dev):
            _book(db, extra, classes["gym_fri"])  # push this one close to its capacity of 8
        _book(db, sara, classes["mma_wed"])
        _book(db, sara, classes["mma_sat"])
        # yoga_thu and mma_sat stay lightly booked on purpose (low utilisation signal).
        # ananya (lapsed) and lisa (no membership) intentionally book nothing.
        print("  booked members into classes at varied fill levels")

    print("  ananya (lapsed package) and lisa (no package) stay idle for churn-style signals")


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
    parser.add_argument(
        "--rich-demo",
        action="store_true",
        help=(
            "Create a full test dataset: 3 trainers, 8 members across every package "
            "(including a lapsed and an unsubscribed one), a week of classes at varied "
            "fill levels, bookings and programmes."
        ),
    )
    args = parser.parse_args()

    wants_admin = bool(args.admin_email or args.admin_password)
    if wants_admin and not (args.admin_email and args.admin_password):
        print("--admin-email and --admin-password go together.", file=sys.stderr)
        return 1
    if not wants_admin and not (args.demo or args.public_demo or args.rich_demo):
        print(
            "Nothing to do: pass admin credentials, --demo, --public-demo or --rich-demo.",
            file=sys.stderr,
        )
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
        if args.rich_demo:
            seed_rich_demo(db)
        db.commit()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
