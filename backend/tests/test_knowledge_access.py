"""Who FitBot may quote the gym's documents to.

The ladder runs visitor, then Starter, then Performance, then Complete, then staff. It is the
package's own allowed_disciplines that decides, so selling a tier and unlocking its material
can never drift apart.
"""

from datetime import date, timedelta

import pytest

from app.agents.workflow import readable_disciplines
from app.db import Membership
from app.services.entitlements import STAFF_ENTITLEMENTS, entitlements_for
from app.services.llm import LLMResult
from tests.conftest import auth_header


@pytest.fixture(autouse=True)
def stub_model(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.LLMChain.generate",
        lambda self, system, prompt: LLMResult(text="A model wrote this."),
    )


def give_package(db_session, member, plans, name):
    plan = next(item for item in plans if item.name == name)
    db_session.add(
        Membership(
            user_id=member.id,
            plan_id=plan.id,
            starts_on=date.today(),
            expires_on=date.today() + timedelta(days=plan.duration_days),
        )
    )
    db_session.commit()
    return plan


# --- The ladder itself ----------------------------------------------------


def test_a_visitor_may_only_read_front_of_house_material():
    assert readable_disciplines(None) == ("reception",)


def test_someone_without_a_package_gets_no_more_than_a_visitor():
    assert readable_disciplines(()) == ("reception",)


@pytest.mark.parametrize(
    ("package", "expected"),
    [
        ("Starter", ("gym", "reception")),
        ("Performance", ("gym", "reception", "yoga")),
        ("Complete", ("gym", "mma", "reception", "yoga")),
    ],
)
def test_each_package_unlocks_one_more_shelf(db_session, member, seeded_plans, package, expected):
    give_package(db_session, member, seeded_plans, package)

    ent = entitlements_for(db_session, member)

    assert readable_disciplines(ent.allowed_disciplines) == expected


def test_staff_read_everything():
    assert readable_disciplines(STAFF_ENTITLEMENTS.allowed_disciplines) == (
        "gym",
        "mma",
        "reception",
        "yoga",
    )


def test_the_ladder_never_shrinks_as_the_package_grows(db_session, member, seeded_plans):
    """A more expensive package must be a superset, never a trade."""
    tiers = ["Starter", "Performance", "Complete"]
    seen = []
    for name in tiers:
        db_session.query(Membership).delete()
        db_session.commit()
        give_package(db_session, member, seeded_plans, name)
        ent = entitlements_for(db_session, member)
        seen.append(set(readable_disciplines(ent.allowed_disciplines)))

    for lower, higher in zip(seen, seen[1:], strict=False):
        assert lower < higher


# --- Enforcement at retrieval --------------------------------------------


def test_retrieval_is_skipped_for_a_discipline_the_package_excludes(monkeypatch):
    """A gym-only member asking about MMA must not have MMA documents pulled in."""
    from app.agents import workflow

    called = []
    monkeypatch.setattr(
        workflow.KnowledgeBase,
        "retrieve",
        lambda self, query, disciplines, limit=3: called.append(disciplines) or [],
    )

    assert workflow._retrieve("armbar escape", "mma", ("gym", "reception"), db=None) == []
    assert called == []


def test_retrieval_runs_for_a_discipline_the_package_includes(monkeypatch):
    from app.agents import workflow

    called = []
    monkeypatch.setattr(
        workflow.KnowledgeBase,
        "retrieve",
        lambda self, query, disciplines, limit=3: called.append(disciplines) or [],
    )

    workflow._retrieve("armbar escape", "mma", ("gym", "mma", "reception"), db=None)

    assert called == [("mma",)]


def test_a_starter_member_asking_about_mma_is_told_what_unlocks_it(
    client, db_session, member, seeded_plans
):
    give_package(db_session, member, seeded_plans, "Starter")
    captured = {}

    def capture(self, system, prompt):
        captured["prompt"] = prompt
        return LLMResult(text="Here is some general advice.")

    from app.services.llm import LLMChain

    original = LLMChain.generate
    LLMChain.generate = capture
    try:
        response = client.post(
            "/api/fitbot/chat",
            headers=auth_header(client, member.email),
            json={"message": "teach me a boxing combination"},
        )
    finally:
        LLMChain.generate = original

    assert response.status_code == 200
    assert "does not include mma" in captured["prompt"]


def test_a_complete_member_is_not_told_anything_is_locked(
    client, db_session, member, seeded_plans
):
    give_package(db_session, member, seeded_plans, "Complete")
    captured = {}

    def capture(self, system, prompt):
        captured["prompt"] = prompt
        return LLMResult(text="Here is a combination.")

    from app.services.llm import LLMChain

    original = LLMChain.generate
    LLMChain.generate = capture
    try:
        client.post(
            "/api/fitbot/chat",
            headers=auth_header(client, member.email),
            json={"message": "teach me a boxing combination"},
        )
    finally:
        LLMChain.generate = original

    assert "does not include" not in captured["prompt"]
