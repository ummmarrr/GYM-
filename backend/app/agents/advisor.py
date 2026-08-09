"""AdvisorAgent: recommends what the admin should do next.

Findings are computed by the rules in services/insights.py, so the advice is the same whether
or not the model is reachable. The model's only job is to write the covering briefing, in
priority order, using nothing but those findings.
"""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.services import insights
from app.services.llm import get_llm

SYSTEM_PROMPT = """You are the business advisor for a gym called Master GYM, writing a short
briefing for the owner.

Rules you must follow:
- Use only the findings given. Never introduce a problem that is not listed.
- Open with one sentence on the overall state of the gym.
- Then walk through the highest priority items first, in plain prose, saying what to do and why.
- Group related items instead of repeating yourself.
- Keep it under 220 words. No headings, no bullet symbols, no congratulating the reader.
- Speak plainly to an owner who is busy, not to an analyst.
"""

ALL_CLEAR = (
    "Every check came back clean: renewals are not due, members have their trainers and "
    "programmes, classes are reasonably full, and FitBot has sources to quote. Nothing needs "
    "your attention right now."
)


class AdvisorState(TypedDict, total=False):
    db: Any
    findings: list[insights.Recommendation]
    summary: str
    briefing: str


def scan(state: AdvisorState) -> AdvisorState:
    db: Session = state["db"]
    findings = insights.build_recommendations(db)
    return {"findings": findings, "summary": insights.summarise(findings)}


def brief(state: AdvisorState) -> AdvisorState:
    findings = state.get("findings", [])
    rendered = "\n\n".join(
        f"[{item.priority.upper()}] {item.category} — {item.title}\n"
        f"Evidence: {item.evidence}\n"
        f"Suggested action: {item.action}\n"
        f"Why it matters: {item.impact}"
        for item in findings
    )
    result = get_llm().generate(
        SYSTEM_PROMPT,
        f"""FINDINGS (the only issues you may discuss):
{rendered}

{insights.horizon_note()}

Write the briefing.""",
    )
    return {"briefing": result.text}


def all_clear(state: AdvisorState) -> AdvisorState:
    return {"briefing": ALL_CLEAR}


def has_findings(state: AdvisorState) -> str:
    return "brief" if state.get("findings") else "clear"


def build_workflow():
    graph = StateGraph(AdvisorState)
    graph.add_node("scan", scan)
    graph.add_node("brief", brief)
    graph.add_node("clear", all_clear)

    graph.add_edge(START, "scan")
    graph.add_conditional_edges("scan", has_findings, {"brief": "brief", "clear": "clear"})
    graph.add_edge("brief", END)
    graph.add_edge("clear", END)
    return graph.compile()


workflow = build_workflow()
