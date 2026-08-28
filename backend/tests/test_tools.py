"""FitBot tools and the shared gym_ops layer the MCP server also calls."""

from datetime import date, timedelta

from app.agents.tools import ToolContext, execute_fitbot_tool
from app.db import ClassSchedule, Membership, utc_now
from app.services import gym_ops


def test_get_pricing_lists_seeded_plans(db_session, seeded_plans):
    text = execute_fitbot_tool("get_pricing", {}, ToolContext(db=db_session))

    assert "Starter" in text
    assert "Rs 1,499" in text


def test_search_knowledge_locks_an_excluded_discipline(db_session):
    ctx = ToolContext(db=db_session, allowed_disciplines=("gym",), is_authenticated=True)
    text = execute_fitbot_tool(
        "search_knowledge",
        {"query": "armbar", "discipline": "mma"},
        ctx,
    )

    assert "does not include mma" in text
    assert ctx.sources == []


def test_request_login_sets_the_widget_action():
    ctx = ToolContext(db=None, is_authenticated=False)
    text = execute_fitbot_tool("request_login", {}, ctx)

    assert ctx.action == "login"
    assert "password" in text.lower()


def test_unknown_tool_does_not_raise():
    result = execute_fitbot_tool("drop_all_users", {}, ToolContext(db=None))

    assert "Unknown tool" in result


def test_the_mcp_server_exposes_the_shared_tools():
    from app.mcp_server import mcp

    names = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert {
        "get_pricing",
        "get_timetable",
        "search_knowledge",
        "get_gym_metrics",
        "book_class",
    } <= names


def test_metric_keys_outside_the_registry_are_dropped(db_session):
    text = gym_ops.metrics_text(db_session, ["drop_all_users", "membership_overview"])

    assert "drop_all_users" not in text
    assert "Members" in text or "member" in text.lower()


def test_book_class_enforces_the_package(db_session, member, seeded_plans):
    plan = next(item for item in seeded_plans if item.name == "Starter")
    db_session.add(
        Membership(
            user_id=member.id,
            plan_id=plan.id,
            starts_on=date.today(),
            expires_on=date.today() + timedelta(days=plan.duration_days),
        )
    )
    session = ClassSchedule(
        name="Evening MMA",
        discipline="mma",
        instructor="Rahul",
        starts_at=utc_now() + timedelta(days=1),
        capacity=10,
    )
    db_session.add(session)
    db_session.commit()

    result = gym_ops.book_class_for_email(db_session, member.email, session.id)

    assert "does not include mma" in result
