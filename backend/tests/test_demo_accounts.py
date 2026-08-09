"""The sign-in page publishes the demo passwords, so those accounts must not be able to
change anything a later visitor would see."""

from app.db import Role
from app.services.llm import LLMResult
from tests.conftest import auth_header, make_user

DEMO_ADMIN = "admin-demo@example.com"
DEMO_MEMBER = "member-demo@example.com"


def test_demo_admin_can_read(client, db_session):
    make_user(db_session, DEMO_ADMIN, Role.ADMIN)
    headers = auth_header(client, DEMO_ADMIN)

    assert client.get("/api/admin/overview", headers=headers).status_code == 200
    assert client.get("/api/admin/people", headers=headers).status_code == 200


def test_real_addresses_are_hidden_from_the_demo_admin(client, db_session):
    make_user(db_session, DEMO_ADMIN, Role.ADMIN)
    make_user(db_session, DEMO_MEMBER, Role.MEMBER)
    make_user(db_session, "owner@gmail.com", Role.ADMIN)

    people = client.get("/api/admin/people", headers=auth_header(client, DEMO_ADMIN)).json()
    by_name = {person["full_name"]: person["email"] for person in people}

    assert by_name["Owner"] == "o****@gmail.com"
    assert by_name["Member-Demo"] == DEMO_MEMBER


def test_demo_admin_cannot_write(client, db_session):
    make_user(db_session, DEMO_ADMIN, Role.ADMIN)
    victim = make_user(db_session, "real.member@example.com", Role.MEMBER)
    headers = auth_header(client, DEMO_ADMIN)

    response = client.patch(
        f"/api/admin/people/{victim.id}", json={"active": False}, headers=headers
    )
    assert response.status_code == 403
    assert "demo" in response.json()["detail"].lower()

    db_session.refresh(victim)
    assert victim.active is True


def test_demo_admin_may_still_ask_the_analyst(client, db_session, monkeypatch):
    """The data agent is the point of the admin tour and its answers are not stored."""
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate",
        lambda self, system, prompt: LLMResult(text="All steady."),
    )
    monkeypatch.setattr("app.services.llm.LLMChain.is_configured", property(lambda self: False))
    make_user(db_session, DEMO_ADMIN, Role.ADMIN)
    headers = auth_header(client, DEMO_ADMIN)

    response = client.post(
        "/api/admin/analyst/ask", json={"question": "How is revenue?"}, headers=headers
    )
    assert response.status_code == 200


def test_demo_member_can_book_but_not_edit_their_profile(client, db_session):
    make_user(db_session, DEMO_MEMBER, Role.MEMBER)
    headers = auth_header(client, DEMO_MEMBER)

    response = client.put("/api/me/profile", json={"goal": "wrecked"}, headers=headers)
    assert response.status_code == 403

    # Booking is capped by seat count and reversible, so the tour keeps it.
    missing_class = client.post("/api/classes/does-not-exist/book", headers=headers)
    assert missing_class.status_code == 404


def test_ordinary_accounts_are_unaffected(client, db_session, member):
    headers = auth_header(client, member.email)
    response = client.put("/api/me/profile", json={"goal": "Run a half marathon"}, headers=headers)
    assert response.status_code == 200
