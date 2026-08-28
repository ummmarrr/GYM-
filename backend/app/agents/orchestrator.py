"""Admin Copilot: a supervisor that delegates to DataAgent and AdvisorAgent.

FitBot stays member-facing. These two specialists are already admin-only; this graph is the
router that sits above them and answers questions that need numbers, recommendations, or both.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents import advisor as advisor_agent
from app.agents import analyst as analyst_agent
from app.services.llm import ToolSpec, get_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Master GYM admin copilot. You supervise two specialist agents
and never invent figures yourself.

Tools:
- ask_data_analyst: live numbers from vetted metric queries (revenue, renewals, attendance,
  trainer load, churn risk, FitBot usage, and more). Always call this for "how many / how much /
  which members / are classes full" questions.
- get_advisor_report: prioritised recommendations computed from the same data. Call this for
  "what should I do / what needs attention / briefing" questions.
- For compound questions ("why is revenue soft and what should I do?"), call BOTH tools.

Rules:
- Use only what the tools return. Never invent a number or a problem.
- Lead with the answer, then supporting detail.
- When both tools ran, weave numbers and actions into one short briefing.
- Name which specialist(s) you used in one short closing line,
  e.g. "Sources: DataAgent, AdvisorAgent."
- Keep it under 280 words. No JSON, no code.
"""

DATA_TERMS = (
    "how much",
    "how many",
    "revenue",
    "money",
    "earning",
    "member",
    "expire",
    "renew",
    "class",
    "trainer",
    "idle",
    "churn",
    "signup",
    "fitbot",
    "utilisation",
    "utilization",
    "attendance",
    "which",
    "who",
)
ADVICE_TERMS = (
    "should i",
    "what should",
    "recommend",
    "advice",
    "briefing",
    "priority",
    "attention",
    "next",
    "fix",
    "improve",
    "problem",
    "issue",
    "risk",
    "action",
)


ORCHESTRATOR_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="ask_data_analyst",
        description=(
            "Ask the DataAgent a question. Returns numbers from vetted SQL metrics only. "
            "Use for revenue, renewals, attendance, trainer load, churn, FitBot usage."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The data question to ask, usually the admin's question.",
                }
            },
            "required": ["question"],
        },
    ),
    ToolSpec(
        name="get_advisor_report",
        description=(
            "Run the AdvisorAgent. Returns a prioritised list of computed recommendations "
            "with evidence and suggested actions. Use for 'what should I do' questions."
        ),
        parameters={"type": "object", "properties": {}},
    ),
)


@dataclass
class OrchestratorContext:
    db: Any
    agents_used: list[str] = field(default_factory=list)
    metrics: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)


def ask_data_analyst(db, question: str) -> tuple[str, list]:
    """Run DataAgent and return (answer text, metrics). Callable as a tool or directly."""
    state = analyst_agent.workflow.invoke({"question": question, "db": db})
    metrics = state.get("metrics") or []
    answer = state.get("answer") or ""
    if metrics:
        tables = "\n\n".join(metric.as_text() for metric in metrics)
        return f"{answer}\n\n--- metric tables ---\n{tables}", metrics
    return answer, metrics


def get_advisor_report(db) -> tuple[str, list]:
    """Run AdvisorAgent and return (briefing text, recommendations)."""
    state = advisor_agent.workflow.invoke({"db": db})
    findings = state.get("findings") or []
    briefing = state.get("briefing") or ""
    summary = state.get("summary") or ""
    rendered = "\n\n".join(
        f"[{item.priority.upper()}] {item.category} — {item.title}\n"
        f"Evidence: {item.evidence}\n"
        f"Action: {item.action}\n"
        f"Impact: {item.impact}"
        for item in findings
    )
    body = briefing
    if summary:
        body = f"Summary: {summary}\n\n{briefing}"
    if rendered:
        body = f"{body}\n\n--- recommendations ---\n{rendered}"
    return body, findings


def execute_orchestrator_tool(name: str, arguments: dict, ctx: OrchestratorContext) -> str:
    args = arguments or {}
    if name == "ask_data_analyst":
        question = str(args.get("question") or "").strip()
        if not question:
            return "ask_data_analyst needs a question."
        text, metrics = ask_data_analyst(ctx.db, question)
        ctx.agents_used.append("DataAgent")
        ctx.metrics.extend(metrics)
        return text
    if name == "get_advisor_report":
        text, findings = get_advisor_report(ctx.db)
        ctx.agents_used.append("AdvisorAgent")
        ctx.recommendations.extend(findings)
        return text
    return f"Unknown tool {name!r}."


def classify_intent(question: str) -> set[str]:
    """Cheap keyword router used when the model is unavailable."""
    text = question.lower()
    wants: set[str] = set()
    if any(term in text for term in DATA_TERMS):
        wants.add("data")
    if any(term in text for term in ADVICE_TERMS):
        wants.add("advice")
    if not wants:
        # Default to both for ambiguous admin questions — safer than refusing.
        wants.update({"data", "advice"})
    return wants


def _keyword_fallback(question: str, ctx: OrchestratorContext) -> str:
    wants = classify_intent(question)
    parts: list[str] = []
    if "data" in wants:
        text, metrics = ask_data_analyst(ctx.db, question)
        ctx.agents_used.append("DataAgent")
        ctx.metrics.extend(metrics)
        parts.append(text)
    if "advice" in wants:
        text, findings = get_advisor_report(ctx.db)
        ctx.agents_used.append("AdvisorAgent")
        ctx.recommendations.extend(findings)
        parts.append(text)
    used = ", ".join(dict.fromkeys(ctx.agents_used)) or "none"
    return "\n\n".join(parts) + f"\n\nSources: {used}."


class OrchestratorState(TypedDict, total=False):
    question: str
    db: Any
    answer: str
    agents_used: list[str]
    metrics: list
    recommendations: list


def respond(state: OrchestratorState) -> OrchestratorState:
    ctx = OrchestratorContext(db=state["db"])
    question = state["question"]
    provider = get_llm()

    if not provider.is_configured:
        answer = _keyword_fallback(question, ctx)
        return {
            "answer": answer,
            "agents_used": list(dict.fromkeys(ctx.agents_used)),
            "metrics": ctx.metrics,
            "recommendations": ctx.recommendations,
        }

    result = provider.generate_with_tools(
        SYSTEM_PROMPT,
        f"The gym owner asked: {question}\n\nCall the right tool(s), then answer.",
        ORCHESTRATOR_TOOLS,
        lambda name, arguments: execute_orchestrator_tool(name, arguments, ctx),
    )
    answer = result.text
    if ctx.agents_used and "Sources:" not in answer:
        used = ", ".join(dict.fromkeys(ctx.agents_used))
        answer = f"{answer}\n\nSources: {used}."
    return {
        "answer": answer,
        "agents_used": list(dict.fromkeys(ctx.agents_used)),
        "metrics": ctx.metrics,
        "recommendations": ctx.recommendations,
    }


def build_workflow():
    graph = StateGraph(OrchestratorState)
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    return graph.compile()


workflow = build_workflow()
