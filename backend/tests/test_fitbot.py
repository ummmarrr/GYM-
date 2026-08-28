"""FitBot over HTTP. The model is stubbed so these stay fast, free and deterministic."""

import pytest

from app.services.llm import LLMResult
from tests.conftest import auth_header


@pytest.fixture(autouse=True)
def stub_model(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate",
        lambda self, system, prompt: LLMResult(text="Here is a simple plan."),
    )
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate_with_tools",
        lambda self, system, prompt, tools, execute, max_rounds=4: LLMResult(
            text="Here is a simple plan."
        ),
    )


def test_a_visitor_can_chat_without_signing_in(client):
    response = client.post("/api/fitbot/chat", json={"message": "how do I start training?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["conversation_id"]
    assert body["action"] == "none"


def test_a_visitor_asking_about_their_plan_is_asked_to_sign_in(client):
    response = client.post("/api/fitbot/chat", json={"message": "when does my plan expire?"})

    assert response.json()["action"] == "login"


def test_fitbot_never_asks_for_a_password(client):
    answer = client.post("/api/fitbot/chat", json={"message": "I want to log in"}).json()["answer"]

    assert "password" not in answer.lower() or "not ask for your password" in answer.lower()


@pytest.mark.parametrize("role", ["admin", "trainer", "member"])
def test_every_signed_in_role_can_chat(client, request, role):
    """Staff have no package, so their entitlement summary must not assume an expiry date."""
    user = request.getfixturevalue(role)

    response = client.post(
        "/api/fitbot/chat",
        headers=auth_header(client, user.email),
        json={"message": "give me a push day workout"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["answer"]


def test_a_member_with_a_package_can_chat(client, db_session, member, seeded_plans):
    from datetime import date, timedelta

    from app.db import Membership

    plan = next(item for item in seeded_plans if item.name == "Performance")
    db_session.add(
        Membership(
            user_id=member.id,
            plan_id=plan.id,
            starts_on=date.today(),
            expires_on=date.today() + timedelta(days=plan.duration_days),
        )
    )
    db_session.commit()

    response = client.post(
        "/api/fitbot/chat",
        headers=auth_header(client, member.email),
        json={"message": "what should I train today?"},
    )

    assert response.status_code == 200, response.text


def test_a_risky_message_is_handed_to_a_human(client):
    response = client.post(
        "/api/fitbot/chat", json={"message": "I get chest pain during cardio"}
    ).json()

    assert response["needs_human_handoff"] is True


def test_the_conversation_is_remembered(client):
    first = client.post("/api/fitbot/chat", json={"message": "hello"}).json()
    second = client.post(
        "/api/fitbot/chat",
        json={"message": "and after that?", "conversation_id": first["conversation_id"]},
    ).json()

    assert second["conversation_id"] == first["conversation_id"]


def test_one_member_cannot_read_another_members_conversation(client, member, trainer):
    owner = auth_header(client, member.email)
    started = client.post("/api/fitbot/chat", headers=owner, json={"message": "hi"}).json()

    intruder = auth_header(client, trainer.email)
    response = client.post(
        "/api/fitbot/chat",
        headers=intruder,
        json={"message": "what did they say?", "conversation_id": started["conversation_id"]},
    )

    assert response.status_code == 403


def test_a_signed_out_visitor_cannot_hijack_a_members_conversation(client, member):
    owner = auth_header(client, member.email)
    started = client.post("/api/fitbot/chat", headers=owner, json={"message": "hi"}).json()

    response = client.post(
        "/api/fitbot/chat",
        json={"message": "continue", "conversation_id": started["conversation_id"]},
    )

    assert response.status_code == 403


def test_the_transcript_is_only_readable_by_its_owner(client, member, trainer):
    owner = auth_header(client, member.email)
    started = client.post("/api/fitbot/chat", headers=owner, json={"message": "hi"}).json()
    conversation_id = started["conversation_id"]

    assert (
        client.get(f"/api/fitbot/conversations/{conversation_id}", headers=owner).status_code == 200
    )
    other = client.get(
        f"/api/fitbot/conversations/{conversation_id}", headers=auth_header(client, trainer.email)
    )
    assert other.status_code == 404
