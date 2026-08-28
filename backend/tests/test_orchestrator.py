"""Admin Copilot: supervisor that delegates to DataAgent and AdvisorAgent."""

from app.agents import orchestrator
from app.agents.orchestrator import OrchestratorContext, execute_orchestrator_tool
from app.services.llm import LLMResult
from tests.conftest import auth_header


def test_classify_intent_spots_data_questions():
    assert "data" in orchestrator.classify_intent("How much revenue have we made?")


def test_classify_intent_spots_advice_questions():
    assert "advice" in orchestrator.classify_intent("What should I do this week?")


def test_classify_intent_defaults_both_when_ambiguous():
    assert orchestrator.classify_intent("Tell me about the gym") == {"data", "advice"}


def test_ask_data_analyst_tool_records_the_agent(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.LLMChain.is_configured",
        property(lambda self: False),
    )
    ctx = OrchestratorContext(db=db_session)
    text = execute_orchestrator_tool(
        "ask_data_analyst",
        {"question": "How much revenue have we made?"},
        ctx,
    )

    assert "DataAgent" in ctx.agents_used
    assert text


def test_get_advisor_report_tool_records_the_agent(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.LLMChain.is_configured",
        property(lambda self: False),
    )
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate",
        lambda self, system, prompt: LLMResult(text="All steady."),
    )
    ctx = OrchestratorContext(db=db_session)
    text = execute_orchestrator_tool("get_advisor_report", {}, ctx)

    assert "AdvisorAgent" in ctx.agents_used
    assert text


def test_unknown_orchestrator_tool_does_not_raise():
    result = execute_orchestrator_tool("drop_all", {}, OrchestratorContext(db=None))
    assert "Unknown tool" in result


def test_copilot_endpoint_is_admin_only(client, member):
    response = client.post(
        "/api/admin/copilot/ask",
        headers=auth_header(client, member.email),
        json={"question": "How is revenue?"},
    )
    assert response.status_code == 403


def test_copilot_endpoint_rejects_anonymous(client):
    response = client.post("/api/admin/copilot/ask", json={"question": "How is revenue?"})
    assert response.status_code == 401


def test_admin_can_ask_the_copilot(client, admin, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.LLMChain.is_configured",
        property(lambda self: False),
    )
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate",
        lambda self, system, prompt: LLMResult(text="Briefing."),
    )
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate_with_tools",
        lambda self, system, prompt, tools, execute, max_rounds=4: LLMResult(
            text=execute("ask_data_analyst", {"question": "How much revenue?"})
        ),
    )

    response = client.post(
        "/api/admin/copilot/ask",
        headers=auth_header(client, admin.email),
        json={"question": "How much revenue have we made?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"]
    assert "DataAgent" in body["agents_used"]
