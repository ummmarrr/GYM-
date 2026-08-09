"""Package entitlements decide what a member may actually do."""

from datetime import date, datetime, timedelta

from app.db import ClassSchedule, Membership, MembershipPlan
from tests.conftest import auth_header


def plan_named(plans, name: str) -> MembershipPlan:
    return next(plan for plan in plans if plan.name == name)


def give_membership(db_session, member, plan, days: int | None = None) -> Membership:
    starts_on = date.today()
    membership = Membership(
        user_id=member.id,
        plan_id=plan.id,
        starts_on=starts_on,
        expires_on=starts_on + timedelta(days=days or plan.duration_days),
    )
    db_session.add(membership)
    db_session.commit()
    return membership


def add_class(db_session, discipline: str, capacity: int = 10) -> ClassSchedule:
    session = ClassSchedule(
        name=f"{discipline.title()} Session",
        discipline=discipline,
        instructor="Coach",
        starts_at=datetime.now() + timedelta(days=2),
        capacity=capacity,
    )
    db_session.add(session)
    db_session.commit()
    return session


def test_plans_are_public(client, seeded_plans):
    response = client.get("/api/plans")

    assert response.status_code == 200
    assert {plan["name"] for plan in response.json()} == {"Starter", "Performance", "Complete"}


def test_member_without_a_package_has_no_entitlements(client, member):
    response = client.get("/api/me/entitlements", headers=auth_header(client, member.email))

    body = response.json()
    assert body["has_active_membership"] is False
    assert body["allowed_disciplines"] == []


def test_purchasing_a_package_grants_its_entitlements(client, member, seeded_plans):
    headers = auth_header(client, member.email)
    performance = plan_named(seeded_plans, "Performance")

    purchase = client.post("/api/me/membership", headers=headers, json={"plan_id": performance.id})
    assert purchase.status_code == 201

    entitlements = client.get("/api/me/entitlements", headers=headers).json()
    assert entitlements["has_active_membership"] is True
    assert entitlements["plan_name"] == "Performance"
    assert entitlements["allowed_disciplines"] == ["gym", "yoga"]
    assert entitlements["personalised_programme"] is True


def test_booking_requires_an_active_membership(client, db_session, member):
    session = add_class(db_session, "gym")

    response = client.post(
        f"/api/classes/{session.id}/book", headers=auth_header(client, member.email)
    )

    assert response.status_code == 403
    assert "active membership" in response.json()["detail"]


def test_starter_package_cannot_book_a_yoga_class(client, db_session, member, seeded_plans):
    give_membership(db_session, member, plan_named(seeded_plans, "Starter"))
    session = add_class(db_session, "yoga")

    response = client.post(
        f"/api/classes/{session.id}/book", headers=auth_header(client, member.email)
    )

    assert response.status_code == 403
    assert "does not include yoga" in response.json()["detail"]


def test_complete_package_can_book_an_mma_class(client, db_session, member, seeded_plans):
    give_membership(db_session, member, plan_named(seeded_plans, "Complete"))
    session = add_class(db_session, "mma")

    response = client.post(
        f"/api/classes/{session.id}/book", headers=auth_header(client, member.email)
    )

    assert response.status_code == 201


def test_the_same_class_cannot_be_booked_twice(client, db_session, member, seeded_plans):
    give_membership(db_session, member, plan_named(seeded_plans, "Complete"))
    session = add_class(db_session, "gym")
    headers = auth_header(client, member.email)

    assert client.post(f"/api/classes/{session.id}/book", headers=headers).status_code == 201
    second = client.post(f"/api/classes/{session.id}/book", headers=headers)

    assert second.status_code == 409


def test_a_full_class_is_refused(client, db_session, member, trainer, seeded_plans):
    give_membership(db_session, member, plan_named(seeded_plans, "Complete"))
    session = add_class(db_session, "gym", capacity=1)

    # The trainer takes the only seat first.
    assert (
        client.post(
            f"/api/classes/{session.id}/book", headers=auth_header(client, trainer.email)
        ).status_code
        == 201
    )
    response = client.post(
        f"/api/classes/{session.id}/book", headers=auth_header(client, member.email)
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This class is full."


def test_an_expired_membership_grants_nothing(client, db_session, member, seeded_plans):
    plan = plan_named(seeded_plans, "Complete")
    db_session.add(
        Membership(
            user_id=member.id,
            plan_id=plan.id,
            starts_on=date.today() - timedelta(days=400),
            expires_on=date.today() - timedelta(days=1),
        )
    )
    db_session.commit()

    entitlements = client.get(
        "/api/me/entitlements", headers=auth_header(client, member.email)
    ).json()

    assert entitlements["has_active_membership"] is False


def test_cancelling_frees_the_seat(client, db_session, member, seeded_plans):
    give_membership(db_session, member, plan_named(seeded_plans, "Complete"))
    session = add_class(db_session, "gym")
    headers = auth_header(client, member.email)
    client.post(f"/api/classes/{session.id}/book", headers=headers)

    cancelled = client.delete(f"/api/classes/{session.id}/book", headers=headers)

    assert cancelled.status_code == 200
    listing = client.get("/api/classes", headers=headers).json()
    assert listing[0]["seats_taken"] == 0
    assert listing[0]["booked_by_me"] is False
