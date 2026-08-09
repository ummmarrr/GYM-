"""Admin-only agents: the data analyst and the advisor.

Both are behind require_admin. Trainers and members have no route to these figures at all.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.advisor import workflow as advisor_workflow
from app.agents.analyst import workflow as analyst_workflow
from app.api.deps import require_admin
from app.db import AuditEvent, User, get_db
from app.schemas import (
    AdvisorReport,
    AnalystAnswer,
    AnalystQuestion,
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
        recommendations=[
            RecommendationItem(
                priority=item.priority,
                category=item.category,
                title=item.title,
                evidence=item.evidence,
                action=item.action,
                impact=item.impact,
            )
            for item in findings
        ],
    )
