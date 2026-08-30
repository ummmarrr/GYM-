"""The two admin agents: routing, guardrails and access control."""

import pytest

from app.agents import analyst
from app.services.llm import LLMResult
from tests.conftest import auth_header


@pytest.fixture(autouse=True)
def stub_model(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate",
        lambda self, system, prompt: LLMResult(text="Revenue is 3,999 rupees from one member."),
    )
    # Unconfigured, so metric selection falls back to keywords instead of asking a model.
    monkeypatch.setattr(
        "app.services.llm.LLMChain.is_configured",
        property(lambda self: False),
    )


# --- Guardrails on what the model may run --------------------------------


def test_a_hallucinated_metric_key_is_discarded():
    assert analyst._parse_keys('["revenue_summary", "drop_all_users", "users.password_hash"]') == [
        "revenue_summary"
    ]


def test_non_json_replies_do_not_crash_the_agent():
    for raw in ["I think revenue", "", "```json\nnot json\n```", "{}"]:
        assert analyst._parse_keys(raw) == []


def test_keys_are_parsed_out_of_a_fenced_reply():
    raw = '```json\n["revenue_summary", "signup_trend"]\n```'

    assert analyst._parse_keys(raw) == ["revenue_summary", "signup_trend"]


def test_at_most_four_metrics_are_ever_run():
    raw = (
        '["revenue_summary", "signup_trend", "expiring_soon", "trainer_load", '
        '"idle_members", "membership_overview"]'
    )

    assert len(analyst._parse_keys(raw)) == 4


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("How much money did we make?", "revenue_summary"),
        ("Whose membership is expiring?", "expiring_soon"),
        ("Are our classes full?", "class_utilisation"),
        ("Which members have gone quiet?", "idle_members"),
        ("How many members do we have?", "membership_overview"),
        ("Is FitBot being used?", "fitbot_activity"),
    ],
)
def test_keyword_routing_covers_the_common_questions(question, expected):
    assert expected in analyst.keyword_keys(question)


def test_an_unrelated_question_selects_nothing():
    assert analyst.keyword_keys("What is the capital of France?") == []


# --- Access control -------------------------------------------------------

ROUTES = [
    ("get", "/api/admin/analyst/metrics"),
    ("get", "/api/admin/advisor/report"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_agent_routes_reject_anonymous_callers(client, method, path):
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_agent_routes_reject_members(client, member, method, path):
    response = getattr(client, method)(path, headers=auth_header(client, member.email))
    assert response.status_code == 403


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_agent_routes_reject_trainers(client, trainer, method, path):
    response = getattr(client, method)(path, headers=auth_header(client, trainer.email))
    assert response.status_code == 403


def test_the_analyst_rejects_a_member(client, member):
    response = client.post(
        "/api/admin/analyst/ask",
        headers=auth_header(client, member.email),
        json={"question": "How much revenue did we make?"},
    )

    assert response.status_code == 403


def test_copilot_rejects_anonymous_and_non_admins(client, member, trainer):
    assert client.post("/api/admin/copilot/ask", json={"question": "How is revenue?"}).status_code == 401
    assert (
        client.post(
            "/api/admin/copilot/ask",
            headers=auth_header(client, member.email),
            json={"question": "How is revenue?"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/copilot/ask",
            headers=auth_header(client, trainer.email),
            json={"question": "How is revenue?"},
        ).status_code
        == 403
    )


# --- Behaviour ------------------------------------------------------------


def test_the_analyst_answers_an_admin_with_the_metrics_it_used(client, admin, seeded_plans):
    response = client.post(
        "/api/admin/analyst/ask",
        headers=auth_header(client, admin.email),
        json={"question": "How much revenue have we made?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert [metric["key"] for metric in body["metrics"]] == ["revenue_summary"]


def test_the_analyst_admits_when_it_cannot_answer(client, admin):
    response = client.post(
        "/api/admin/analyst/ask",
        headers=auth_header(client, admin.email),
        json={"question": "What is the capital of France?"},
    )

    body = response.json()
    assert body["metrics"] == []
    assert "do not track" in body["answer"]


def test_asking_the_analyst_is_recorded_in_the_audit_log(client, admin, db_session):
    from app.db import AuditEvent

    client.post(
        "/api/admin/analyst/ask",
        headers=auth_header(client, admin.email),
        json={"question": "How many members do we have?"},
    )

    event = db_session.query(AuditEvent).filter(AuditEvent.action == "analyst.queried").one()
    assert event.actor_id == admin.id
    assert "membership_overview" in event.detail


def test_the_metrics_endpoint_returns_the_whole_registry(client, admin):
    from app.services import analytics

    response = client.get("/api/admin/analyst/metrics", headers=auth_header(client, admin.email))

    assert response.status_code == 200
    assert {metric["key"] for metric in response.json()} == set(analytics.REGISTRY)


def test_the_advisor_reports_findings_with_evidence(client, admin):
    response = client.get("/api/admin/advisor/report", headers=auth_header(client, admin.email))

    assert response.status_code == 200
    body = response.json()
    assert body["briefing"]
    assert body["recommendations"]
    for item in body["recommendations"]:
        assert item["evidence"]
        assert item["action"]
        assert item["priority"] in {"high", "medium", "low"}


def test_the_analyst_streams_an_answer(client, admin, seeded_plans, db_session):
    from app.db import AuditEvent

    response = client.post(
        "/api/admin/analyst/ask/stream",
        headers=auth_header(client, admin.email),
        json={"question": "How much revenue have we made?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: token" in response.text
    assert "event: done" in response.text
    assert "revenue_summary" in response.text
    assert db_session.query(AuditEvent).filter(AuditEvent.action == "analyst.queried").count() == 1


def test_the_advisor_streams_a_briefing(client, admin):
    response = client.get(
        "/api/admin/advisor/report/stream",
        headers=auth_header(client, admin.email),
    )

    assert response.status_code == 200
    assert "event: meta" in response.text
    assert "event: token" in response.text
    assert "event: done" in response.text
    assert "recommendations" in response.text


def test_the_copilot_streams_an_answer(client, admin, seeded_plans, db_session):
    from app.db import AuditEvent

    response = client.post(
        "/api/admin/copilot/ask/stream",
        headers=auth_header(client, admin.email),
        json={"question": "How much revenue have we made?"},
    )

    assert response.status_code == 200
    assert "event: token" in response.text
    assert "event: done" in response.text
    assert (
        db_session.query(AuditEvent).filter(AuditEvent.action == "copilot.queried").count() == 1
    )
