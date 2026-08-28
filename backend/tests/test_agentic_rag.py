"""Agentic RAG: one relevance grade and at most one reformulated retrieve."""

from app.services import gym_ops
from app.services.rag import RetrievedChunk

WEAK = RetrievedChunk(text="How to book a class online.", source="reception.pdf", page=1)
STRONG = RetrievedChunk(
    text="Stand with the bar on the upper back. Sit between the hips until thighs are parallel.",
    source="squat.pdf",
    page=3,
)


def test_unreadable_grade_keeps_the_first_retrieve():
    assert gym_ops.parse_retrieval_grade("not json") == (True, "")
    assert gym_ops.parse_retrieval_grade('{"enough": false}') == (True, "")


def test_a_clear_fail_returns_a_rewrite():
    enough, rewrite = gym_ops.parse_retrieval_grade(
        '{"enough": false, "rewrite": "improve squat depth cues"}'
    )
    assert enough is False
    assert rewrite == "improve squat depth cues"


def test_locked_shelf_never_retrieves_or_grades(monkeypatch):
    called = []
    monkeypatch.setattr(
        gym_ops,
        "retrieve_chunks",
        lambda *args, **kwargs: called.append(args) or [],
    )
    monkeypatch.setattr(
        gym_ops,
        "grade_retrieval",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not grade")),
    )

    text, chunks = gym_ops.search_documents(None, "armbar", "mma", ("gym", "reception"))

    assert "does not include mma" in text
    assert chunks == []
    assert called == []


def test_empty_shelf_skips_the_judge(monkeypatch):
    grades = []
    monkeypatch.setattr(gym_ops, "retrieve_chunks", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        gym_ops, "grade_retrieval", lambda *a, **k: grades.append(1) or (False, "retry")
    )

    text, chunks = gym_ops.search_documents(None, "squat", "gym", ("gym", "reception"))

    assert "No matching documents" in text
    assert chunks == []
    assert grades == []


def test_a_weak_first_pass_retrieves_once_more_on_the_same_shelf(monkeypatch):
    queries: list[str] = []

    def fake_retrieve(db, query, discipline, allowed, limit=3):
        queries.append(query)
        assert discipline == "gym"
        assert "mma" not in allowed
        return [WEAK] if query == "thing" else [STRONG]

    monkeypatch.setattr(gym_ops, "retrieve_chunks", fake_retrieve)
    monkeypatch.setattr(
        gym_ops, "grade_retrieval", lambda question, chunks: (False, "improve squat depth")
    )

    text, chunks = gym_ops.search_documents(None, "thing", "gym", ("gym", "reception"))

    assert queries == ["thing", "improve squat depth"]
    assert chunks == [STRONG]
    assert "Retrieval was refined once" in text
    assert "squat.pdf" in text


def test_enough_chunks_do_not_spend_a_second_retrieve(monkeypatch):
    queries: list[str] = []

    def fake_retrieve(db, query, discipline, allowed, limit=3):
        queries.append(query)
        return [STRONG]

    monkeypatch.setattr(gym_ops, "retrieve_chunks", fake_retrieve)
    monkeypatch.setattr(gym_ops, "grade_retrieval", lambda question, chunks: (True, ""))

    text, chunks = gym_ops.search_documents(None, "squat depth", "gym", ("gym",))

    assert queries == ["squat depth"]
    assert chunks == [STRONG]
    assert "refined" not in text


def test_grade_is_skipped_when_no_llm_is_configured(monkeypatch):
    class Quiet:
        is_configured = False

    monkeypatch.setattr(gym_ops, "get_llm", lambda: Quiet())

    enough, rewrite = gym_ops.grade_retrieval("squat?", [STRONG])
    assert enough is True
    assert rewrite == ""


def test_at_most_two_retrieves(monkeypatch):
    queries: list[str] = []

    def fake_retrieve(db, query, discipline, allowed, limit=3):
        queries.append(query)
        return [WEAK]

    monkeypatch.setattr(gym_ops, "retrieve_chunks", fake_retrieve)
    monkeypatch.setattr(
        gym_ops,
        "grade_retrieval",
        lambda question, chunks: (False, f"rewrite-{len(queries)}"),
    )

    gym_ops.search_documents(None, "first", "gym", ("gym",))

    assert len(queries) == 2
