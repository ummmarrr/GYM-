"""FitBot decision logic. These run without any network call."""

import pytest

from app.agents.workflow import (
    LOGIN_PROMPT,
    SAFETY_RESPONSE,
    SIGNUP_PROMPT,
    UPGRADE_PROMPT,
    classify_route,
    safety_gate,
    triage,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What does a monthly package cost?", "reception"),
        ("Teach me surya namaskar", "yoga"),
        ("How do I improve my muay thai clinch?", "mma"),
        ("Give me a push day split", "gym"),
        ("When does my membership expire?", "account"),
    ],
)
def test_classify_route(message, expected):
    assert classify_route(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "I get chest pain when I run",
        "I think I have a slipped disc, what should I do",
        "Which steroid should I take to bulk",
    ],
)
def test_safety_gate_blocks_medical_and_doping_questions(message):
    result = safety_gate({"message": message})

    assert result["safe"] is False
    assert result["answer"] == SAFETY_RESPONSE
    assert result["needs_human_handoff"] is True


def test_safety_gate_allows_ordinary_training_questions():
    result = safety_gate({"message": "How many sets of squats should a beginner do?"})

    assert result["safe"] is True
    assert result["needs_human_handoff"] is False


def test_visitor_asking_about_their_account_is_sent_to_login():
    result = triage({"message": "when does my plan expire?", "is_authenticated": False})

    assert result["action"] == "login"
    assert result["answer"] == LOGIN_PROMPT


def test_visitor_asking_to_join_is_sent_to_signup():
    result = triage({"message": "I want to sign up", "is_authenticated": False})

    assert result["action"] == "signup"
    assert result["answer"] == SIGNUP_PROMPT


def test_visitor_asking_a_training_question_is_answered_without_login():
    result = triage({"message": "how do I deadlift safely", "is_authenticated": False})

    assert result["action"] == "none"
    assert result["route"] == "gym"


def test_member_without_the_entitlement_is_offered_an_upgrade():
    result = triage(
        {
            "message": "can you make me a personalised diet chart",
            "is_authenticated": True,
            "can_personalise": False,
        }
    )

    assert result["action"] == "upgrade"
    assert result["answer"] == UPGRADE_PROMPT


def test_member_with_the_entitlement_reaches_the_model():
    result = triage(
        {
            "message": "can you make me a personalised diet chart",
            "is_authenticated": True,
            "can_personalise": True,
        }
    )

    assert result["action"] == "none"
