"""Questions the database already holds, now fetched when the model calls a tool."""

from datetime import timedelta

import pytest

from app.agents.workflow import classify_front_desk
from app.db import ClassSchedule, utc_now
from app.services.llm import LLMResult
from tests.conftest import auth_header

MODEL_REPLY = "A model wrote this."


@pytest.fixture(autouse=True)
def stub_model(monkeypatch):
    """Anything the model answers is recognisable, so a tool-backed reply is obvious."""
    from app.agents.workflow import classify_front_desk

    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate",
        lambda self, system, prompt: LLMResult(text=MODEL_REPLY),
    )

    def generate_with_tools(self, system, prompt, tools, execute, max_rounds=4):
        question = prompt.rsplit("Q:", 1)[-1].strip() if "Q:" in prompt else prompt
        kind = classify_front_desk(question)
        if kind == "pricing":
            return LLMResult(text=execute("get_pricing", {}))
        if kind == "timetable":
            result = execute("get_timetable", {})
            if result.startswith("No classes"):
                return LLMResult(text=MODEL_REPLY)
            return LLMResult(text=result)
        return LLMResult(text=MODEL_REPLY)

    monkeypatch.setattr("app.services.llm.LLMChain.generate_with_tools", generate_with_tools)


def ask(client, message, headers=None):
    return client.post(
        "/api/fitbot/chat", json={"message": message}, headers=headers or {}
    ).json()["answer"]


# --- Classification -------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("How much do your packages cost?", "pricing"),
        ("what are the fees", "pricing"),
        ("Tell me about your plans", "pricing"),
        ("what is the timetable this week", "timetable"),
        ("when is the yoga class", "timetable"),
        ("what time does the mma session start", "timetable"),
        # These belong to the member, not the public price list.
        ("when does my package expire?", None),
        ("show me my plan", None),
        # Coaching, even though it says "plan".
        ("make me a plan for fat loss", None),
        ("my diet plan please", None),
        # Nothing the database knows.
        ("how do I deadlift safely?", None),
    ],
)
def test_front_desk_questions_are_recognised(message, expected):
    assert classify_front_desk(message) == expected


# --- Pricing --------------------------------------------------------------


def test_a_price_question_is_answered_from_the_database(client, seeded_plans):
    answer = ask(client, "How much do your packages cost?")

    assert "Starter" in answer
    assert "Performance" in answer
    assert MODEL_REPLY not in answer


def test_the_quoted_price_matches_the_plan_record(client, seeded_plans):
    answer = ask(client, "what are your fees?")

    # 149900 paise is Rs 1,499. An invented price would not match.
    assert "Rs 1,499" in answer


def test_a_visitor_gets_prices_without_signing_in(client, seeded_plans):
    """Pricing is the most common public question, so it must not need an account."""
    answer = ask(client, "pricing please")

    assert "Starter" in answer


def test_asking_about_your_own_package_does_not_return_the_price_list(
    client, member, seeded_plans
):
    answer = ask(client, "when does my package expire?", auth_header(client, member.email))

    assert "Starter" not in answer


# --- Timetable ------------------------------------------------------------


def test_the_timetable_is_answered_from_the_schedule(client, db_session):
    db_session.add(
        ClassSchedule(
            name="Sunrise Yoga",
            discipline="yoga",
            instructor="Meera",
            starts_at=utc_now() + timedelta(days=1),
            capacity=15,
        )
    )
    db_session.commit()

    answer = ask(client, "what is the timetable this week?")

    assert "Sunrise Yoga" in answer
    assert "Meera" in answer
    assert MODEL_REPLY not in answer


def test_a_class_beyond_the_window_is_not_listed(client, db_session):
    db_session.add(
        ClassSchedule(
            name="Distant Boxing",
            discipline="mma",
            instructor="Rahul",
            starts_at=utc_now() + timedelta(days=30),
            capacity=10,
        )
    )
    db_session.commit()

    assert "Distant Boxing" not in ask(client, "what is the timetable this week?")


def test_an_empty_timetable_falls_back_to_the_model(client):
    """With nothing scheduled there is no fact to state, so the model should reply instead."""
    assert ask(client, "what is the timetable this week?") == MODEL_REPLY
