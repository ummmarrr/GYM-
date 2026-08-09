from app.db import Role, User
from tests.conftest import auth_header, make_user


def test_register_returns_a_token_and_creates_a_member(client, db_session):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "New.Person@Example.com",
            "full_name": "New Person",
            "password": "StrongPass123",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "member"
    assert body["access_token"]

    # Email is normalised so "New.Person@Example.com" cannot be registered twice.
    saved = db_session.query(User).filter(User.email == "new.person@example.com").one()
    assert saved.role is Role.MEMBER


def test_register_rejects_a_duplicate_email(client, member):
    response = client.post(
        "/api/auth/register",
        json={"email": member.email, "full_name": "Impostor", "password": "StrongPass123"},
    )

    assert response.status_code == 409


def test_register_rejects_a_short_password(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "full_name": "Short Pass", "password": "abc"},
    )

    assert response.status_code == 422


def test_self_signup_cannot_grant_an_elevated_role(client, db_session):
    client.post(
        "/api/auth/register",
        json={
            "email": "sneaky@example.com",
            "full_name": "Sneaky",
            "password": "StrongPass123",
            "role": "admin",
        },
    )

    saved = db_session.query(User).filter(User.email == "sneaky@example.com").one()
    assert saved.role is Role.MEMBER


def test_login_with_a_wrong_password_is_rejected(client, member):
    response = client.post(
        "/api/auth/login", json={"email": member.email, "password": "WrongPassword"}
    )

    assert response.status_code == 401
    # The message must not reveal whether the email exists.
    assert response.json()["detail"] == "Incorrect email or password."


def test_login_for_an_unknown_email_gives_the_same_message(client):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "WrongPassword"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


def test_deactivated_account_cannot_log_in(client, db_session):
    user = make_user(db_session, "gone@example.com", Role.MEMBER)
    user.active = False
    db_session.commit()

    response = client.post("/api/auth/login", json={"email": user.email, "password": "Password123"})

    assert response.status_code == 403


def test_me_requires_a_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_the_signed_in_user(client, member):
    response = client.get("/api/auth/me", headers=auth_header(client, member.email))

    assert response.status_code == 200
    assert response.json()["email"] == member.email
