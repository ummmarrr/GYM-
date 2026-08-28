"""Admin-only agents: the data analyst, the advisor, and the copilot that orchestrates both.

All three are behind require_admin. Trainers and members have no route to these figures at all.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.advisor import workflow as advisor_workflow
from app.agents.analyst import workflow as analyst_workflow
from app.agents.orchestrator import workflow as orchestrator_workflow
from app.api.deps import require_admin
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
    state = analyst_workflow.invoke({"question": payload.question, "db": db})
    metrics = state.get("metrics", [])

    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="analyst.queried",
            resource_type="analytics",
            resource_id=None,
            detail=f"{payload.question[:200]} -> {[metric.key for metric in metrics]}",
        )
    )
    db.commit()

    return AnalystAnswer(
        question=payload.question,
        answer=state["answer"],
        metrics=[_as_table(metric) for metric in metrics],
    )


@router.get("/advisor/report", response_model=AdvisorReport)
def advisor_report(
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    state = advisor_workflow.invoke({"db": db})
    findings = state.get("findings", [])

    return AdvisorReport(
        summary=state.get("summary") or "No issues found.",
        briefing=state["briefing"],
        recommendations=[_as_recommendation(item) for item in findings],
    )


@router.post("/copilot/ask", response_model=CopilotAnswer)
def ask_copilot(
    payload: CopilotQuestion,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Supervisor that delegates to DataAgent and/or AdvisorAgent."""
    state = orchestrator_workflow.invoke({"question": payload.question, "db": db})
    agents = state.get("agents_used") or []
    metrics = state.get("metrics") or []
    findings = state.get("recommendations") or []

    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="copilot.queried",
            resource_type="orchestrator",
            resource_id=None,
            detail=f"{payload.question[:200]} -> agents={agents}",
        )
    )
    db.commit()

    return CopilotAnswer(
        question=payload.question,
        answer=state["answer"],
        agents_used=agents,
        metrics=[_as_table(metric) for metric in metrics],
        recommendations=[_as_recommendation(item) for item in findings],
    )
