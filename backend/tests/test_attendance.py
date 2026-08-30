from datetime import date, timedelta

from app.db import (
    Attendance,
    ClassBooking,
    ClassSchedule,
    FitnessProfile,
    GymNotice,
    Membership,
    Role,
    utc_now,
)
from tests.conftest import auth_header, make_user


def reception_user(db_session):
    return make_user(db_session, "reception@example.com", Role.RECEPTION)


def test_reception_has_front_desk_access_but_not_admin_or_trainer_permissions(
    client, db_session, member
):
    reception = reception_user(db_session)
    headers = auth_header(client, reception.email)

    assert client.get("/api/front-desk/search?q=member", headers=headers).status_code == 200
    assert client.get("/api/admin/people", headers=headers).status_code == 403
    assert client.get("/api/trainer/members", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/staff/classes",
            headers=headers,
            json={
                "name": "Reception class",
                "discipline": "gym",
                "instructor": "No",
                "starts_at": (utc_now() + timedelta(days=1)).isoformat(),
                "capacity": 10,
            },
        ).status_code
        == 403
    )


def test_trainer_cannot_use_front_desk_lookup(client, trainer):
    response = client.post(
        "/api/front-desk/lookup",
        headers=auth_header(client, trainer.email),
        json={"token": "x" * 20},
    )
    assert response.status_code == 403


def test_pass_lookup_and_rotation_revokes_old_token(client, db_session, member):
    reception = reception_user(db_session)
    member_headers = auth_header(client, member.email)
    desk_headers = auth_header(client, reception.email)

    first = client.get("/api/me/pass", headers=member_headers)
    assert first.status_code == 200
    first_token = first.json()["token"]
    assert first.json()["qr_payload"] == first_token
    assert client.get("/api/me/pass", headers=member_headers).json()["token"] == first_token

    lookup = client.post(
        "/api/front-desk/lookup", headers=desk_headers, json={"token": first_token}
    )
    assert lookup.status_code == 200
    assert lookup.json()["member"]["id"] == member.id

    rotated = client.post(
        f"/api/staff/members/{member.id}/pass/rotate", headers=desk_headers
    )
    assert rotated.status_code == 200
    assert rotated.json()["token"] != first_token
    assert (
        client.post(
            "/api/front-desk/lookup", headers=desk_headers, json={"token": first_token}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/front-desk/lookup",
            headers=desk_headers,
            json={"token": rotated.json()["token"]},
        ).status_code
        == 200
    )


def test_check_in_is_idempotent_for_four_hours(client, db_session, member):
    reception = reception_user(db_session)
    headers = auth_header(client, reception.email)
    payload = {"user_id": member.id, "method": "manual"}

    first = client.post("/api/front-desk/check-in", headers=headers, json=payload)
    second = client.post("/api/front-desk/check-in", headers=headers, json=payload)

    assert first.status_code == 200
    assert first.json()["already_checked_in"] is False
    assert second.status_code == 200
    assert second.json()["already_checked_in"] is True
    assert second.json()["attendance"]["id"] == first.json()["attendance"]["id"]
    assert db_session.query(Attendance).count() == 1


def test_expired_membership_warns_but_allows_check_in(
    client, db_session, member, seeded_plans
):
    reception = reception_user(db_session)
    db_session.add(
        Membership(
            user_id=member.id,
            plan_id=seeded_plans[0].id,
            starts_on=date.today() - timedelta(days=60),
            expires_on=date.today() - timedelta(days=30),
            status="active",
        )
    )
    db_session.commit()

    response = client.post(
        "/api/front-desk/check-in",
        headers=auth_header(client, reception.email),
        json={"user_id": member.id, "method": "manual"},
    )

    assert response.status_code == 200
    assert response.json()["already_checked_in"] is False
    assert response.json()["briefing"]["entitlements"]["has_active_membership"] is False
    assert any("expired" in warning.lower() for warning in response.json()["briefing"]["warnings"])


def test_briefing_includes_classes_trainer_notices_and_last_check_in(
    client, db_session, member, trainer, seeded_plans
):
    reception = reception_user(db_session)
    scheduled = ClassSchedule(
        name="Tomorrow Yoga",
        discipline="yoga",
        instructor=trainer.full_name,
        trainer_id=trainer.id,
        starts_at=utc_now() + timedelta(days=1),
        capacity=12,
    )
    db_session.add_all(
        [
            FitnessProfile(user_id=member.id, assigned_trainer_id=trainer.id),
            scheduled,
            GymNotice(
                kind="repair",
                title="Treadmill repair",
                message="One treadmill is unavailable.",
                active_from=utc_now() - timedelta(hours=1),
                active_until=utc_now() + timedelta(days=1),
                created_by_id=reception.id,
            ),
            Membership(
                user_id=member.id,
                plan_id=seeded_plans[0].id,
                starts_on=date.today(),
                expires_on=date.today() + timedelta(days=20),
                status="active",
            ),
        ]
    )
    db_session.flush()
    db_session.add(ClassBooking(class_id=scheduled.id, member_id=member.id))
    db_session.commit()
    headers = auth_header(client, reception.email)
    client.post(
        "/api/front-desk/check-in",
        headers=headers,
        json={"user_id": member.id, "method": "qr"},
    )

    response = client.get(f"/api/front-desk/briefing/{member.id}", headers=headers)
    body = response.json()

    assert response.status_code == 200
    assert body["trainer_name"] == trainer.full_name
    assert body["upcoming_classes"][0]["name"] == "Tomorrow Yoga"
    assert body["active_notices"][0]["title"] == "Treadmill repair"
    assert body["last_check_in"]["method"] == "qr"
    assert body["entitlements"]["plan_name"] == seeded_plans[0].name


def test_self_signup_cannot_request_reception(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "self-reception@example.com",
            "full_name": "Self Reception",
            "password": "Password123",
            "role": "reception",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "member"


def test_reception_can_enroll_photo_and_member_can_view_it(client, db_session, member, trainer):
    reception = reception_user(db_session)
    image = b"\x89PNG\r\n\x1a\n" + b"small-test-image"

    uploaded = client.put(
        f"/api/staff/members/{member.id}/photo",
        headers=auth_header(client, reception.email),
        files={"photo": ("member.png", image, "image/png")},
    )
    assert uploaded.status_code == 200

    viewed = client.get(
        f"/api/staff/members/{member.id}/photo",
        headers=auth_header(client, member.email),
    )
    assert viewed.status_code == 200
    assert viewed.content == image
    assert viewed.headers["content-type"] == "image/png"

    forbidden = client.get(
        f"/api/staff/members/{member.id}/photo",
        headers=auth_header(client, trainer.email),
    )
    assert forbidden.status_code == 403


def test_admin_manages_notices_and_reception_reads_them(client, db_session, admin):
    reception = reception_user(db_session)
    payload = {
        "kind": "repair",
        "title": "Cable machine maintenance",
        "message": "Use the second-floor cable station.",
        "active_from": (utc_now() - timedelta(minutes=5)).isoformat(),
        "active_until": None,
    }

    created = client.post(
        "/api/front-desk/notices",
        headers=auth_header(client, admin.email),
        json=payload,
    )
    assert created.status_code == 201

    listed = client.get(
        "/api/front-desk/notices",
        headers=auth_header(client, reception.email),
    )
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == payload["title"]

    forbidden = client.post(
        "/api/front-desk/notices",
        headers=auth_header(client, reception.email),
        json=payload,
    )
    assert forbidden.status_code == 403
