"""Admin-only agents: the data analyst, the advisor, and the copilot that orchestrates both.

All three are behind require_admin. Trainers and members have no route to these figures at all.
JSON endpoints remain; `/stream` variants deliver the prose progressively over SSE.
"""

import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.advisor import workflow as advisor_workflow
from app.agents.analyst import workflow as analyst_workflow
from app.agents.orchestrator import workflow as orchestrator_workflow
from app.api.deps import require_admin
from app.api.sse import event_stream, sse, text_chunks
from app.db import AuditEvent, User, get_db
from app.schemas import (
    AdvisorReport,
    AnalystAnswer,
    AnalystQuestion,
    CopilotAnswer,
    CopilotQuestion,
    MetricTable,
    RecommendationItem,
)
from app.services import analytics

router = APIRouter(prefix="/admin", tags=["admin intelligence"])
logger = logging.getLogger(__name__)


def _as_table(metric: analytics.Metric) -> MetricTable:
    return MetricTable(
        key=metric.key,
        title=metric.title,
        headline=metric.headline,
        columns=metric.columns,
        rows=metric.rows,
    )


def _as_recommendation(item) -> RecommendationItem:
    return RecommendationItem(
        priority=item.priority,
        category=item.category,
        title=item.title,
        evidence=item.evidence,
        action=item.action,
        impact=item.impact,
    )


def _run_analyst(db: Session, question: str) -> AnalystAnswer:
    state = analyst_workflow.invoke({"question": question, "db": db})
    metrics = state.get("metrics", [])
    return AnalystAnswer(
        question=question,
        answer=state["answer"],
        metrics=[_as_table(metric) for metric in metrics],
    )


def _run_advisor(db: Session) -> AdvisorReport:
    state = advisor_workflow.invoke({"db": db})
    findings = state.get("findings", [])
    return AdvisorReport(
        summary=state.get("summary") or "No issues found.",
        briefing=state["briefing"],
        recommendations=[_as_recommendation(item) for item in findings],
    )


def _run_copilot(db: Session, question: str) -> CopilotAnswer:
    state = orchestrator_workflow.invoke({"question": question, "db": db})
    agents = state.get("agents_used") or []
    metrics = state.get("metrics") or []
    findings = state.get("recommendations") or []
    return CopilotAnswer(
        question=question,
        answer=state["answer"],
        agents_used=agents,
        metrics=[_as_table(metric) for metric in metrics],
        recommendations=[_as_recommendation(item) for item in findings],
    )


def _audit(db: Session, actor_id: str, action: str, resource_type: str, detail: str) -> None:
    db.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=None,
            detail=detail,
        )
    )
    db.commit()


@router.get("/analyst/metrics", response_model=list[MetricTable])
def all_metrics(
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Every metric, computed. Powers the dashboard cards without involving the model."""
    return [_as_table(metric) for metric in analytics.run_all(db).values()]


@router.post("/analyst/ask", response_model=AnalystAnswer)
def ask_analyst(
    payload: AnalystQuestion,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    answer = _run_analyst(db, payload.question)
    _audit(
        db,
        current_user.id,
        "analyst.queried",
        "analytics",
        f"{payload.question[:200]} -> {[metric.key for metric in answer.metrics]}",
    )
    return answer


@router.post("/analyst/ask/stream")
def ask_analyst_stream(
    payload: AnalystQuestion,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    def events() -> Iterator[str]:
        try:
            answer = _run_analyst(db, payload.question)
            yield sse("meta", {"question": answer.question})
            for text in text_chunks(answer.answer):
                yield sse("token", {"text": text})
            _audit(
                db,
                current_user.id,
                "analyst.queried",
                "analytics",
                f"{payload.question[:200]} -> {[metric.key for metric in answer.metrics]}",
            )
            yield sse(
                "done",
                {
                    "question": answer.question,
                    "metrics": [metric.model_dump() for metric in answer.metrics],
                },
            )
        except Exception:
            logger.exception("Analyst stream failed")
            db.rollback()
            yield sse(
                "error",
                {"message": "The analyst could not answer that. Please try again."},
            )

    return event_stream(events())


@router.get("/advisor/report", response_model=AdvisorReport)
def advisor_report(
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return _run_advisor(db)


@router.get("/advisor/report/stream")
def advisor_report_stream(
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    def events() -> Iterator[str]:
        try:
            report = _run_advisor(db)
            yield sse("meta", {"summary": report.summary})
            for text in text_chunks(report.briefing):
                yield sse("token", {"text": text})
            yield sse(
                "done",
                {
                    "summary": report.summary,
                    "recommendations": [item.model_dump() for item in report.recommendations],
                },
            )
        except Exception:
            logger.exception("Advisor stream failed")
            db.rollback()
            yield sse(
                "error",
                {"message": "Could not build the report. Please try again."},
            )

    return event_stream(events())


@router.post("/copilot/ask", response_model=CopilotAnswer)
def ask_copilot(
    payload: CopilotQuestion,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Supervisor that delegates to DataAgent and/or AdvisorAgent."""
    answer = _run_copilot(db, payload.question)
    _audit(
        db,
        current_user.id,
        "copilot.queried",
        "orchestrator",
        f"{payload.question[:200]} -> agents={answer.agents_used}",
    )
    return answer


@router.post("/copilot/ask/stream")
def ask_copilot_stream(
    payload: CopilotQuestion,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    def events() -> Iterator[str]:
        try:
            answer = _run_copilot(db, payload.question)
            yield sse(
                "meta",
                {"question": answer.question, "agents_used": answer.agents_used},
            )
            for text in text_chunks(answer.answer):
                yield sse("token", {"text": text})
            _audit(
                db,
                current_user.id,
                "copilot.queried",
                "orchestrator",
                f"{payload.question[:200]} -> agents={answer.agents_used}",
            )
            yield sse(
                "done",
                {
                    "question": answer.question,
                    "agents_used": answer.agents_used,
                    "metrics": [metric.model_dump() for metric in answer.metrics],
                    "recommendations": [item.model_dump() for item in answer.recommendations],
                },
            )
        except Exception:
            logger.exception("Copilot stream failed")
            db.rollback()
            yield sse(
                "error",
                {"message": "The copilot could not answer that. Please try again."},
            )

    return event_stream(events())
