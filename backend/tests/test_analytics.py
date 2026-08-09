"""The analyst is only trustworthy if the numbers underneath it are right."""

from datetime import date, timedelta

from app.db import ClassBooking, ClassSchedule, FitnessProfile, Membership, Programme, Role, utc_now
from app.services import analytics, insights
from tests.conftest import make_user


def give(db_session, member, plan, days: int | None = None) -> Membership:
    membership = Membership(
        user_id=member.id,
        plan_id=plan.id,
        starts_on=date.today(),
        expires_on=date.today() + timedelta(days=days if days is not None else plan.duration_days),
    )
    db_session.add(membership)
    db_session.commit()
    return membership


def plan_named(plans, name):
    return next(plan for plan in plans if plan.name == name)


def add_class(db_session, discipline, capacity=10, trainer_id=None):
    session = ClassSchedule(
        name=f"{discipline} session",
        discipline=discipline,
        instructor="Coach",
        trainer_id=trainer_id,
        starts_at=utc_now() + timedelta(days=3),
        capacity=capacity,
    )
    db_session.add(session)
    db_session.commit()
    return session


def test_every_registered_metric_runs_on_an_empty_database(db_session):
    """A brand new gym must not crash the analyst with divide-by-zero or missing rows."""
    for key, spec in analytics.REGISTRY.items():
        metric = spec.run(db_session)
        assert metric.key == key
        assert metric.headline


def test_membership_overview_counts_active_lapsed_and_never(db_session, seeded_plans):
    plan = plan_named(seeded_plans, "Starter")
    active = make_user(db_session, "active@example.com", Role.MEMBER)
    lapsed = make_user(db_session, "lapsed@example.com", Role.MEMBER)
    make_user(db_session, "never@example.com", Role.MEMBER)

    give(db_session, active, plan)
    db_session.add(
        Membership(
            user_id=lapsed.id,
            plan_id=plan.id,
            starts_on=date.today() - timedelta(days=60),
            expires_on=date.today() - timedelta(days=5),
        )
    )
    db_session.commit()

    headline = analytics.membership_overview(db_session).headline

    assert "3 members registered" in headline
    assert "1 hold an active package" in headline
    assert "1 have lapsed" in headline
    assert "1 never subscribed" in headline


def test_revenue_only_counts_sold_memberships(db_session, seeded_plans, member):
    performance = plan_named(seeded_plans, "Performance")
    give(db_session, member, performance)

    metric = analytics.revenue_summary(db_session)

    assert analytics.rupees(performance.price_paise) in metric.headline
    assert metric.rows[0]["package"] == "Performance"
    assert metric.rows[0]["sold"] == 1


def test_expiring_soon_respects_the_window(db_session, seeded_plans):
    plan = plan_named(seeded_plans, "Starter")
    soon = make_user(db_session, "soon@example.com", Role.MEMBER)
    later = make_user(db_session, "later@example.com", Role.MEMBER)
    give(db_session, soon, plan, days=3)
    give(db_session, later, plan, days=90)

    rows = analytics.expiring_soon(db_session).rows

    assert [row["member"] for row in rows] == ["Soon"]
    assert rows[0]["days left"] == 3


def test_class_utilisation_computes_fill_rate(db_session, seeded_plans, member):
    give(db_session, member, plan_named(seeded_plans, "Complete"))
    session = add_class(db_session, "gym", capacity=4)
    db_session.add(ClassBooking(class_id=session.id, member_id=member.id))
    db_session.commit()

    rows = {row["discipline"]: row for row in analytics.class_utilisation(db_session).rows}

    assert rows["gym"]["seats"] == 4
    assert rows["gym"]["booked"] == 1
    assert rows["gym"]["fill"] == "25%"
    # No yoga classes exist, so a fill rate would be meaningless rather than zero.
    assert rows["yoga"]["fill"] == "n/a"


def test_missing_programmes_only_flags_entitled_members(db_session, seeded_plans, trainer):
    starter_member = make_user(db_session, "starter@example.com", Role.MEMBER)
    performance_member = make_user(db_session, "perf@example.com", Role.MEMBER)
    served_member = make_user(db_session, "served@example.com", Role.MEMBER)

    give(db_session, starter_member, plan_named(seeded_plans, "Starter"))
    give(db_session, performance_member, plan_named(seeded_plans, "Performance"))
    give(db_session, served_member, plan_named(seeded_plans, "Performance"))
    db_session.add(
        Programme(
            member_id=served_member.id,
            trainer_id=trainer.id,
            kind="workout",
            title="Done",
            content="Squat 3x8",
        )
    )
    db_session.commit()

    rows = analytics.missing_programmes(db_session).rows

    # Starter does not include a programme, and the served member already has one.
    assert [row["email"] for row in rows] == ["perf@example.com"]


def test_unassigned_members_ignores_members_with_a_trainer(db_session, seeded_plans, trainer):
    assigned = make_user(db_session, "assigned@example.com", Role.MEMBER)
    alone = make_user(db_session, "alone@example.com", Role.MEMBER)
    give(db_session, assigned, plan_named(seeded_plans, "Performance"))
    give(db_session, alone, plan_named(seeded_plans, "Performance"))
    db_session.add(FitnessProfile(user_id=assigned.id, assigned_trainer_id=trainer.id))
    db_session.commit()

    rows = analytics.unassigned_members(db_session).rows

    assert [row["email"] for row in rows] == ["alone@example.com"]


def test_idle_members_flags_paying_members_who_stopped_booking(db_session, seeded_plans):
    booker = make_user(db_session, "booker@example.com", Role.MEMBER)
    quiet = make_user(db_session, "quiet@example.com", Role.MEMBER)
    give(db_session, booker, plan_named(seeded_plans, "Complete"))
    give(db_session, quiet, plan_named(seeded_plans, "Complete"))
    session = add_class(db_session, "gym")
    db_session.add(ClassBooking(class_id=session.id, member_id=booker.id))
    db_session.commit()

    rows = analytics.idle_members(db_session).rows

    assert [row["member"] for row in rows] == ["Quiet"]


def test_knowledge_coverage_reports_empty_disciplines(db_session):
    metric = analytics.knowledge_coverage(db_session)

    assert "No sources for" in metric.headline
    assert all(row["documents"] == 0 for row in metric.rows)


# --- Recommendation rules ------------------------------------------------


def titles(recommendations) -> str:
    return " || ".join(item.title for item in recommendations)


def test_recommendations_are_ordered_by_priority(db_session, seeded_plans, member):
    give(db_session, member, plan_named(seeded_plans, "Performance"), days=2)

    found = insights.build_recommendations(db_session)

    priorities = [insights.PRIORITY_ORDER[item.priority] for item in found]
    assert priorities == sorted(priorities)


def test_an_unfulfilled_programme_promise_is_high_priority(db_session, seeded_plans, member):
    give(db_session, member, plan_named(seeded_plans, "Performance"))

    found = insights.build_recommendations(db_session)
    match = next(item for item in found if "never got" in item.title)

    assert match.priority == "high"
    assert member.full_name in match.evidence


def test_an_empty_timetable_is_flagged(db_session):
    found = insights.build_recommendations(db_session)

    assert "The timetable is empty" in titles(found)


def test_a_healthy_gym_produces_fewer_findings(db_session, seeded_plans, trainer, member):
    """Fixing the underlying problems must actually remove the recommendations."""
    before = insights.build_recommendations(db_session)

    give(db_session, member, plan_named(seeded_plans, "Complete"), days=120)
    db_session.add(FitnessProfile(user_id=member.id, assigned_trainer_id=trainer.id))
    db_session.add(
        Programme(
            member_id=member.id,
            trainer_id=trainer.id,
            kind="workout",
            title="Block 1",
            content="Squat 3x8",
        )
    )
    for discipline in analytics.DISCIPLINES:
        session = add_class(db_session, discipline, capacity=2, trainer_id=trainer.id)
        db_session.add(ClassBooking(class_id=session.id, member_id=member.id))
    db_session.commit()

    after = insights.build_recommendations(db_session)
    after_titles = titles(after)

    assert len(after) < len(before)
    assert "never got" not in after_titles
    assert "The timetable is empty" not in after_titles
    assert "no trainers on the roster" not in after_titles


def test_summarise_counts_by_priority(db_session):
    found = insights.build_recommendations(db_session)

    summary = insights.summarise(found)

    assert str(len(found)) in summary


def test_summarise_handles_a_clean_run():
    assert "No issues found" in insights.summarise([])
