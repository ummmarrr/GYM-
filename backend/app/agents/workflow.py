"""FitBot: the Master GYM conversational assistant.

The graph is deliberately explicit. Safety is checked before anything else, then a triage
node decides whether the request can be answered at all (auth needed, package does not
cover it) before we spend a model call.
"""

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.llm import get_llm
from app.services.rag import KnowledgeBase, RetrievedChunk

logger = logging.getLogger(__name__)

BOT_NAME = "FitBot"

# Prompt budget. The free Gemini tier caps tokens per minute and per day as well as requests,
# so a smaller prompt directly buys more conversations before the quota runs out.
CHUNK_CHAR_BUDGET = 500
CONTEXT_CHAR_BUDGET = 1500
RETRIEVAL_LIMIT = 3

COACHING_ROUTES = frozenset({"gym", "yoga", "mma"})
ACCOUNT_ROUTES = frozenset({"account", "reception"})
KNOWN_DISCIPLINES = frozenset({"gym", "yoga", "mma", "reception"})

# Everyone may read front-of-house material, whatever they have paid. The rest of the ladder
# comes from the package's own allowed_disciplines: gym, then yoga, then mma.
PUBLIC_DISCIPLINES = ("reception",)


def readable_disciplines(allowed: tuple[str, ...] | None) -> tuple[str, ...]:
    """Which document shelves this caller may draw on."""
    return tuple(sorted({*PUBLIC_DISCIPLINES, *(allowed or ())}))

# Every token here is resent on each call, so the wording is deliberately terse. The
# per-call prompt in respond() must not repeat any of these instructions.
SYSTEM_PROMPT = f"""You are {BOT_NAME} at Master GYM, acting as receptionist, gym trainer,
yoga coach or MMA coach as the question requires. Be warm, concrete and brief: specific sets,
reps, holds and progressions rather than vague encouragement.

Rules:
- No diagnosis, no medication, no extreme dieting or water cuts, no unsupervised sparring.
- Never invent prices, class timings or account details. If a fact is not in the context, say
  so and offer to connect them to reception.
- Never ask for a password, OTP or card number.
- Say what you are unsure about when the documents do not support an answer.
- Reply in the member's language, including Hindi or Hinglish.
- Coaching answers: brief warm-up, main work with sets and reps, one clear stop condition.
- Not a member yet and asking about training? Answer helpfully, then mention the fitting package.
- End with a "Sources:" line only when documents were actually used."""

SAFETY_RESPONSE = (
    "That sounds like something a qualified professional should look at rather than me. "
    "Please stop any activity that hurts, and speak to a doctor or physiotherapist first. "
    "Once you have been cleared, tell me your limitations and I will happily work around them. "
    "I can also pass this to a Master GYM trainer if you would like."
)

LOGIN_PROMPT = (
    "Happy to help with that. Please sign in first using the secure form below, then ask me "
    "again and I will pull up your details."
)

SIGNUP_PROMPT = (
    "Great, let's get you started at Master GYM. Create your account using the secure form "
    "below. It takes about a minute, and I will not ask for your password in this chat."
)

UPGRADE_PROMPT = (
    "A personalised programme is part of our Performance and Complete packages. Your current "
    "package does not include it, but I can still answer general training questions. "
    "Would you like to see the upgrade options?"
)

AUTH_TERMS = ("log in", "login", "log-in", "sign in", "signin", "my account")
SIGNUP_TERMS = (
    "sign up",
    "signup",
    "register",
    "create an account",
    "new member",
    "join gym",
    "join the gym",
)
ACCOUNT_TERMS = (
    "my plan",
    "my package",
    "my membership",
    "my booking",
    "expire",
    "expiry",
    "renew",
    "dues",
    "my programme",
    "my program",
)
PERSONAL_PROGRAMME_TERMS = (
    "make me a plan",
    "personalised",
    "personalized",
    "custom plan",
    "plan for me",
    "my workout plan",
    "my diet plan",
    "diet chart",
    "routine for me",
)
RECEPTION_TERMS = (
    "price",
    "pricing",
    "cost",
    "fee",
    "package",
    "timing",
    "open",
    "close",
    "schedule",
    "class",
    "trial",
    "location",
    "address",
)
# Questions the database answers exactly. Kept next to the other routing vocabulary so all
# of FitBot's intent detection stays readable in one place.
PRICING_TERMS = (
    "price",
    "pricing",
    "cost",
    "how much",
    "fee",
    "fees",
    "charges",
    "package",
    "packages",
    "membership plan",
    "plans",
    "subscription",
)
TIMETABLE_TERMS = (
    "timetable",
    "timing",
    "timings",
    "schedule",
    "what time",
    "when is",
    "when are",
    "class list",
    "classes this week",
    "upcoming class",
)
YOGA_TERMS = ("yoga", "asana", "pranayama", "meditation", "flexibility", "surya namaskar")
MMA_TERMS = (
    "mma",
    "boxing",
    "kickboxing",
    "sparring",
    "grappling",
    "bjj",
    "muay thai",
    "wrestling",
)
HIGH_RISK_TERMS = (
    "chest pain",
    "faint",
    "dizzy",
    "pregnant",
    "medication",
    "eating disorder",
    "self harm",
    "suicide",
    "rehabilitation",
    "diagnose",
    "steroid",
    "anabolic",
)
INJURY_TERMS = (
    "injury",
    "injured",
    "fracture",
    "torn",
    "severe pain",
    "concussion",
    "slipped disc",
)


class FitBotState(TypedDict, total=False):
    message: str
    history: str
    display_name: str
    role: str
    profile: str
    entitlements: str
    is_authenticated: bool
    can_personalise: bool
    allowed_disciplines: tuple[str, ...]
    scripted: str
    db: object
    route: str
    safe: bool
    answer: str
    sources: list[RetrievedChunk]
    action: str
    needs_human_handoff: bool


def _mentions(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def classify_front_desk(message: str) -> str | None:
    """Name the front-desk question this is, or None if the model should answer it.

    "My package expires when?" is about one member's account and "make me a plan" is coaching,
    so neither may be answered with the public price list even though both mention a package.
    """
    text = message.lower()
    if _mentions(text, ACCOUNT_TERMS) or _mentions(text, PERSONAL_PROGRAMME_TERMS):
        return None
    if _mentions(text, PRICING_TERMS):
        return "pricing"
    if _mentions(text, TIMETABLE_TERMS):
        return "timetable"
    return None


def classify_route(message: str) -> str:
    text = message.lower()
    if _mentions(text, ACCOUNT_TERMS):
        return "account"
    if _mentions(text, YOGA_TERMS):
        return "yoga"
    if _mentions(text, MMA_TERMS):
        return "mma"
    if _mentions(text, RECEPTION_TERMS):
        return "reception"
    return "gym"


def safety_gate(state: FitBotState) -> FitBotState:
    text = state["message"].lower()
    if _mentions(text, HIGH_RISK_TERMS) or _mentions(text, INJURY_TERMS):
        return {
            "safe": False,
            "answer": SAFETY_RESPONSE,
            "action": "none",
            "needs_human_handoff": True,
            "sources": [],
        }
    return {"safe": True, "needs_human_handoff": False}


def triage(state: FitBotState) -> FitBotState:
    """Decide whether we can answer at all, before spending a model call."""
    text = state["message"].lower()
    authenticated = state.get("is_authenticated", False)
    route = classify_route(state["message"])

    if not authenticated:
        if _mentions(text, SIGNUP_TERMS):
            return {"route": "auth", "answer": SIGNUP_PROMPT, "action": "signup", "sources": []}
        if _mentions(text, AUTH_TERMS) or route == "account":
            return {"route": "auth", "answer": LOGIN_PROMPT, "action": "login", "sources": []}

    if (
        authenticated
        and _mentions(text, PERSONAL_PROGRAMME_TERMS)
        and not state.get("can_personalise", False)
    ):
        return {"route": "account", "answer": UPGRADE_PROMPT, "action": "upgrade", "sources": []}

    # Prices and timings were read from the database before the graph ran, so there is nothing
    # left for the model to add.
    scripted = state.get("scripted")
    if scripted:
        return {"route": "reception", "answer": scripted, "action": "none", "sources": []}

    return {"route": route, "action": "none"}


def route_after_safety(state: FitBotState) -> str:
    return "triage" if state.get("safe") else "finish"


def route_after_triage(state: FitBotState) -> str:
    """Anything that already produced an answer skips the model call entirely."""
    return "finish" if state.get("answer") else "respond"


def _retrieve(message: str, route: str, disciplines: tuple[str, ...], db) -> list[RetrievedChunk]:
    discipline = route if route in KNOWN_DISCIPLINES else "reception"
    # The package decides which shelves are readable; the question decides which one to read.
    if discipline not in disciplines:
        return []
    try:
        return KnowledgeBase(db).retrieve(message, (discipline,), limit=RETRIEVAL_LIMIT)
    except Exception:
        # The assistant must keep working even if retrieval is unavailable.
        logger.exception("Retrieval failed, answering without documents")
        return []


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks inside a character budget.

    Chunks are stored at 1200 characters, so passing four of them verbatim costs more than
    every other part of the prompt combined. The head of a chunk carries the match.
    """
    parts: list[str] = []
    used = 0
    for chunk in chunks:
        text = _clip(chunk.text, CHUNK_CHAR_BUDGET)
        if used + len(text) > CONTEXT_CHAR_BUDGET:
            break
        parts.append(f"[{chunk.source} p{chunk.page or '?'}] {text}")
        used += len(text)
    return "\n".join(parts) or "none matched"


def build_prompt(state: FitBotState, chunks: list[RetrievedChunk], locked: bool = False) -> str:
    """Assemble the smallest prompt that still answers this particular question.

    Membership details are irrelevant to a squat-technique question and a fitness profile is
    irrelevant to an opening-hours question, so neither is sent unless the route needs it.
    """
    route = state.get("route", "gym")
    lines = [f"Desk: {route}"]

    name = state.get("display_name")
    role = state.get("role", "visitor")
    lines.append(f"Member: {name} ({role})" if name else "Signed-out visitor")

    entitlements = state.get("entitlements")
    if route in ACCOUNT_ROUTES and entitlements:
        lines.append(f"Package: {entitlements}")

    profile = state.get("profile")
    if route in COACHING_ROUTES and profile and "No fitness profile" not in profile:
        lines.append(f"Profile: {profile}")

    history = state.get("history")
    if history:
        lines.append(f"Earlier:\n{history}")

    lines.append(f"Docs: {_context(chunks)}")
    if locked:
        lines.append(
            f"Note: their package does not include {route}. Answer generally from your own "
            "knowledge, then mention the package that unlocks our full material."
        )
    lines.append(f"Q: {state['message']}")
    return "\n".join(lines)


def respond(state: FitBotState) -> FitBotState:
    route = state.get("route", "gym")
    disciplines = readable_disciplines(state.get("allowed_disciplines"))
    chunks = _retrieve(state["message"], route, disciplines, state.get("db"))
    locked = route in COACHING_ROUTES and route not in disciplines
    prompt = build_prompt(state, chunks, locked=locked)
    logger.info(
        "FitBot call: route=%s prompt=~%d tokens",
        state.get("route", "gym"),
        (len(SYSTEM_PROMPT) + len(prompt)) // 4,
    )
    result = get_llm().generate(SYSTEM_PROMPT, prompt)
    return {"answer": result.text, "sources": chunks, "action": "none"}


def build_workflow():
    graph = StateGraph(FitBotState)
    graph.add_node("safety_gate", safety_gate)
    graph.add_node("triage", triage)
    graph.add_node("respond", respond)

    graph.add_edge(START, "safety_gate")
    graph.add_conditional_edges(
        "safety_gate", route_after_safety, {"triage": "triage", "finish": END}
    )
    graph.add_conditional_edges("triage", route_after_triage, {"respond": "respond", "finish": END})
    graph.add_edge("respond", END)
    return graph.compile()


workflow = build_workflow()
