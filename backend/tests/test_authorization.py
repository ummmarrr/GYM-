"""Role boundaries. Each of these would be a real privilege-escalation bug if it failed."""

import pytest

from tests.conftest import auth_header

ADMIN_ONLY = [
    ("get", "/api/admin/people", None),
    ("get", "/api/admin/overview", None),
    ("get", "/api/admin/knowledge/documents", None),
]


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ONLY)
def test_admin_endpoints_reject_anonymous_callers(client, method, path, payload):
    response = getattr(client, method)(path)
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ONLY)
def test_admin_endpoints_reject_members(client, member, method, path, payload):
    response = getattr(client, method)(path, headers=auth_header(client, member.email))
    assert response.status_code == 403


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ONLY)
def test_admin_endpoints_reject_trainers(client, trainer, method, path, payload):
    response = getattr(client, method)(path, headers=auth_header(client, trainer.email))
    assert response.status_code == 403


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ONLY)
def test_admin_endpoints_allow_admins(client, admin, method, path, payload):
    response = getattr(client, method)(path, headers=auth_header(client, admin.email))
    assert response.status_code == 200


def test_member_cannot_create_a_class(client, member):
    response = client.post(
        "/api/staff/classes",
        headers=auth_header(client, member.email),
        json={
            "name": "Ghost Class",
            "discipline": "gym",
            "instructor": "Nobody",
            "starts_at": "2030-01-01T07:00:00",
            "capacity": 10,
        },
    )

    assert response.status_code == 403


def test_trainer_can_create_a_class(client, trainer):
    response = client.post(
        "/api/staff/classes",
        headers=auth_header(client, trainer.email),
        json={
            "name": "Morning Strength",
            "discipline": "gym",
            "instructor": trainer.full_name,
            "starts_at": "2030-01-01T07:00:00",
            "capacity": 10,
        },
    )

    assert response.status_code == 201


def test_member_cannot_write_a_programme(client, member):
    response = client.post(
        "/api/staff/programmes",
        headers=auth_header(client, member.email),
        json={
            "member_id": member.id,
            "kind": "workout",
            "title": "Self assigned",
            "content": "Only trainers may do this.",
        },
    )

    assert response.status_code == 403


def test_trainer_cannot_write_a_programme_for_an_unassigned_member(client, trainer, member):
    response = client.post(
        "/api/staff/programmes",
        headers=auth_header(client, trainer.email),
        json={
            "member_id": member.id,
            "kind": "workout",
            "title": "Not my member",
            "content": "This trainer was never assigned to them.",
        },
    )

    assert response.status_code == 403


def test_trainer_can_write_a_programme_for_an_assigned_member(client, admin, trainer, member):
    assigned = client.post(
        f"/api/admin/people/{member.id}/trainer/{trainer.id}",
        headers=auth_header(client, admin.email),
    )
    assert assigned.status_code == 200

    response = client.post(
        "/api/staff/programmes",
        headers=auth_header(client, trainer.email),
        json={
            "member_id": member.id,
            "kind": "workout",
            "title": "Beginner full body",
            "content": "Squat 3x8, bench 3x8, row 3x10.",
        },
    )

    assert response.status_code == 201
    assert response.json()["trainer_id"] == trainer.id


def test_admin_cannot_change_their_own_role(client, admin):
    response = client.post(
        f"/api/admin/people/{admin.id}/role",
        headers=auth_header(client, admin.email),
        json={"role": "member"},
    )

    assert response.status_code == 400


def test_admin_cannot_deactivate_themselves(client, admin):
    response = client.patch(
        f"/api/admin/people/{admin.id}",
        headers=auth_header(client, admin.email),
        json={"active": False},
    )

    assert response.status_code == 400
