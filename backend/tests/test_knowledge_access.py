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


def test_parent_child_chunking_ingestion(db_session, tmp_path):
    from app.services.rag import KnowledgeBase
    from app.db import KnowledgeChunk

    # Stub embed_documents to avoid calling Gemini API
    from app.services.embeddings import GeminiEmbedder
    orig_embed = GeminiEmbedder.embed_documents
    GeminiEmbedder.embed_documents = lambda self, texts: [[0.1] * 768 for _ in texts]
    
    class MockPage:
        def __init__(self, text):
            self._text = text
        def get_text(self):
            return self._text
            
    # Page text long enough to have multiple chunks (e.g. 3000 chars)
    page_text = " ".join([f"Word{i}" for i in range(500)])
    
    class MockDoc:
        def __init__(self, text):
            self.pages = [MockPage(text)]
        def __iter__(self):
            return iter(self.pages)
            
    import pymupdf
    orig_open = pymupdf.open
    pymupdf.open = lambda path: MockDoc(page_text)
    
    try:
        kb = KnowledgeBase(db_session)
        # Create a dummy file
        dummy_file = tmp_path / "dummy.pdf"
        dummy_file.write_bytes(b"dummy")
        result = kb.ingest_pdf(dummy_file, "gym")
        assert result.chunk_count > 0
        
        # Verify stored chunks in db
        chunks = db_session.query(KnowledgeChunk).filter(KnowledgeChunk.source == "dummy.pdf").all()
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.parent_content is not None
            assert chunk.content in chunk.parent_content
            assert len(chunk.parent_content) >= len(chunk.content)
    finally:
        GeminiEmbedder.embed_documents = orig_embed
        pymupdf.open = orig_open


def test_hybrid_search_sqlite_fallback(db_session):
    from app.services.rag import KnowledgeBase
    from app.db import KnowledgeChunk
    from app.services.embeddings import GeminiEmbedder
    
    orig_embed_query = GeminiEmbedder.embed_query
    GeminiEmbedder.embed_query = lambda self, text: [0.1] * 768
    
    try:
        # Clear existing knowledge chunks to avoid side effects
        db_session.query(KnowledgeChunk).delete()
        db_session.commit()
        
        # Add chunks with different overlap
        chunk1 = KnowledgeChunk(
            document_hash="hash1",
            source="doc1.pdf",
            page=1,
            discipline="gym",
            content="Do deep squats for building leg strength.",
            parent_content="Parent: Do deep squats for building leg strength. This is excellent for quads.",
            embedding=str([0.1] * 768)
        )
        chunk2 = KnowledgeChunk(
            document_hash="hash2",
            source="doc2.pdf",
            page=1,
            discipline="gym",
            content="Running on the treadmill improves cardiovascular endurance.",
            parent_content="Parent: Running on the treadmill improves cardiovascular endurance. Keep a steady pace.",
            embedding=str([0.1] * 768)
        )
        db_session.add_all([chunk1, chunk2])
        db_session.commit()
        
        kb = KnowledgeBase(db_session)
        # Retrieve asking about "squats"
        results = kb.retrieve("give me some squats workout", ["gym"], limit=2)
        
        assert len(results) == 2
        # The first result should be chunk1 because of keyword overlap ("squats" is in chunk1)
        assert "squats" in results[0].text.lower()
        # Verify it returns parent_content
        assert results[0].text == chunk1.parent_content
        assert results[1].text == chunk2.parent_content
    finally:
        GeminiEmbedder.embed_query = orig_embed_query
