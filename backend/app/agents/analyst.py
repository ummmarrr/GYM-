"""DataAgent: the admin's data analyst.

The model picks which vetted metrics to read and then explains them. It never writes SQL and
never sees a row we did not deliberately hand it, so it cannot reach password hashes or member
chat transcripts, and every figure in the answer traces back to a real query.
"""

import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.services import analytics
from app.services.llm import get_llm

SYSTEM_PROMPT = """You are the data analyst for a gym called Master GYM, speaking to the owner.

Rules you must follow:
- Use only the figures in the DATA section. Never estimate, extrapolate or invent a number.
- If the data does not answer the question, say exactly what is missing.
- Lead with the answer in one sentence, then the supporting detail.
- Be concrete and short. No filler, no congratulating the reader.
- Where a number implies an action, say so in one line at the end.
- Write plain prose with the occasional short list. Never output JSON or code.
"""

NO_MATCH = (
    "I do not track anything that answers that yet. I can report on memberships, revenue, "
    "signups, renewals, class utilisation, trainer workload, unassigned members, unfulfilled "
    "programmes, quiet members, knowledge base coverage and FitBot usage."
)

# Used when the model is unavailable, and to catch obvious intent cheaply.
KEYWORD_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("revenue", "money", "earning", "income", "sales", "paid", "rupee"), "revenue_summary"),
    (("expire", "expiring", "renewal", "renew", "lapse"), "expiring_soon"),
    (("signup", "sign up", "growth", "new member", "joined", "trend"), "signup_trend"),
    (
        ("class", "utilisation", "utilization", "booking", "seat", "attendance", "full"),
        "class_utilisation",
    ),
    (("trainer", "coach", "staff", "workload"), "trainer_load"),
    (("unassigned", "no trainer", "without a trainer"), "unassigned_members"),
    (("programme", "program", "diet plan", "workout plan"), "missing_programmes"),
    (("idle", "quiet", "churn", "inactive", "stopped", "risk"), "idle_members"),
    (("knowledge", "document", "pdf", "source"), "knowledge_coverage"),
    (("fitbot", "chat", "conversation", "bot usage"), "fitbot_activity"),
    (
        ("member", "membership", "package", "plan", "how many", "total", "subscriber"),
        "membership_overview",
    ),
]


class AnalystState(TypedDict, total=False):
    question: str
    db: Any
    keys: list[str]
    metrics: list[analytics.Metric]
    answer: str


def keyword_keys(question: str) -> list[str]:
    text = question.lower()
    keys = [key for terms, key in KEYWORD_HINTS if any(term in text for term in terms)]
    # Preserve order but drop duplicates.
    return list(dict.fromkeys(keys))[:4]


def _parse_keys(raw: str) -> list[str]:
    """Pull metric keys out of the model's reply, tolerating fences and stray prose."""
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    # Anything not in the registry is discarded, so a hallucinated key cannot run.
    return [item for item in parsed if isinstance(item, str) and item in analytics.REGISTRY][:4]


def choose(state: AnalystState) -> AnalystState:
    question = state["question"]
    provider = get_llm()

    keys: list[str] = []
    if provider.is_configured:
        result = provider.generate(
            "You select data sources. Reply with a JSON array of metric keys and nothing else.",
            f"""Available metrics:
{analytics.catalogue()}

Question: {question}

Return the 1 to 3 metric keys that best answer it, as a JSON array of strings.
If none are relevant, return [].""",
        )
        keys = _parse_keys(result.text)

    if not keys:
        keys = keyword_keys(question)

    return {"keys": keys}


def gather(state: AnalystState) -> AnalystState:
    db: Session = state["db"]
    return {"metrics": analytics.run_metrics(db, state.get("keys", []))}


def narrate(state: AnalystState) -> AnalystState:
    metrics = state.get("metrics", [])
    data = "\n\n".join(metric.as_text() for metric in metrics)
    result = get_llm().generate(
        SYSTEM_PROMPT,
        f"""DATA (the only figures you may use):
{data}

The owner asked: {state["question"]}

Answer them.""",
    )
    return {"answer": result.text}


def has_data(state: AnalystState) -> str:
    return "narrate" if state.get("keys") else "nothing"


def nothing(_: AnalystState) -> AnalystState:
    return {"answer": NO_MATCH, "metrics": []}


def build_workflow():
    graph = StateGraph(AnalystState)
    graph.add_node("choose", choose)
    graph.add_node("gather", gather)
    graph.add_node("narrate", narrate)
    graph.add_node("nothing", nothing)

    graph.add_edge(START, "choose")
    graph.add_conditional_edges("choose", has_data, {"narrate": "gather", "nothing": "nothing"})
    graph.add_edge("gather", "narrate")
    graph.add_edge("narrate", END)
    graph.add_edge("nothing", END)
    return graph.compile()


workflow = build_workflow()
