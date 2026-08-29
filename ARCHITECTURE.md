# Master GYM — Full Architecture & Agent Reference

This document is the deep technical reference for the whole system: every backend module, the
FitBot conversational agent, the admin multi-agent orchestrator (Copilot), the two MCP servers,
retrieval, data model, and the frontend. It complements the shorter `README.md`,
`backend/BACKEND.md`, `frontend/FRONTEND.md` and `EXPLANATION.md` — this file goes one level
deeper and stays focused on **how the AI/agent layer actually works**.

---

## 1. Technology stack

| Layer | Technology | Why |
|---|---|---|
| Backend framework | **FastAPI** (Python 3.11+) | Async-ready, typed request/response models via Pydantic, automatic OpenAPI docs. |
| Agent orchestration | **LangGraph** (`langgraph`) | Explicit state graphs instead of an implicit agent loop — safety and auth branches are code, not prompt-controlled. |
| LLM providers | **Google Gemini** (`google-genai`) primary, **Groq** (Llama 3.1 8B, OpenAI-compatible HTTP) fallback | Free-tier friendly; automatic failover when one provider's quota is exhausted. |
| Embeddings | **Gemini `gemini-embedding-001`** (768-dim, truncated from 3072 native) | Avoids running a local embedding model on a 512 MB free-tier host. |
| Vector store | **PostgreSQL + `pgvector`** (Neon serverless Postgres) | Chunks and vectors live in the same DB as everything else; HNSW cosine index for ANN search. |
| ORM | **SQLAlchemy 2.0** (typed `Mapped[...]` models) | Single `db.py` module defines every table; SQLite fallback for local dev/tests. |
| PDF parsing | **PyMuPDF + Gemini vision OCR** | Detect scanned vs text; direct extract or OCR; tables + image summary/detail. |
| Auth | **JWT (`PyJWT`)** + **Argon2 (`pwdlib`)** | Stateless bearer tokens; Argon2 for password hashing (memory-hard, GPU-resistant). |
| Agent tool protocol | **Model Context Protocol (MCP)**, `mcp>=1.9.0` | Two standalone MCP servers expose gym operations and the admin Copilot to any MCP client (Cursor, Claude Desktop, etc.). |
| Rate limiting | In-process sliding window (`core/rate_limit.py`) | No Redis needed for a single free-tier instance. |
| Frontend | **React 18 + TypeScript + Vite + Tailwind CSS v4** | Fast dev server, utility-first styling, typed API client. |
| Testing | **pytest** (193 backend tests), **Playwright** (E2E), **Ruff** (lint) | |
| Hosting (free tier) | Render (API), Cloudflare Pages (frontend), Neon (Postgres) | |

---

## 2. High-level system map

```
                         ┌─────────────────────────────┐
                         │        React Frontend        │
                         │  (Landing / Packages / Join / │
                         │   Member / Trainer / Admin)   │
                         └───────────────┬───────────────┘
                                         │ REST (JWT bearer)
                         ┌───────────────▼───────────────┐
                         │           FastAPI              │
                         │  auth · membership · people ·   │
                         │  knowledge · fitbot · intelligence│
                         └───────────────┬───────────────┘
                    ┌────────────────────┼──────────────────────┐
                    │                    │                      │
          ┌─────────▼────────┐  ┌────────▼─────────┐  ┌─────────▼─────────┐
          │   FitBot graph    │  │  Analyst / Advisor │  │   Copilot graph   │
          │ (member-facing)   │  │   agents (admin)   │  │ (admin supervisor)│
          └─────────┬────────┘  └────────┬─────────┘  └─────────┬─────────┘
                    │                    │                      │
                    └────────────────────┼──────────────────────┘
                                         │
                         ┌───────────────▼───────────────┐
                         │     app/services/gym_ops.py     │  ← single source of truth
                         │  (pricing, timetable, search,   │    for agent + MCP tools
                         │   metrics, booking, retrieval)  │
                         └───────────────┬───────────────┘
                    ┌────────────────────┼──────────────────────┐
          ┌─────────▼────────┐  ┌────────▼─────────┐  ┌─────────▼─────────┐
          │   PostgreSQL +    │  │   LLM chain       │  │   MCP servers      │
          │   pgvector (Neon) │  │ Gemini → Groq     │  │ mcp_server.py      │
          │                   │  │ (services/llm.py) │  │ mcp_admin.py       │
          └───────────────────┘  └───────────────────┘  └───────────────────┘
```

Two independent MCP servers sit **beside** the FastAPI app and call the exact same
`gym_ops` functions, so an MCP client (Cursor, Claude Desktop) and the web app can never
drift apart in behaviour.

---

## 3. FitBot — the member-facing conversational agent

**File:** `backend/app/agents/workflow.py`, tools in `backend/app/agents/tools.py`.

### 3.1 Design philosophy

FitBot is **not** a single giant system prompt with a model deciding everything. It is a
**LangGraph state graph** with three nodes, where the two nodes that make *permission*
decisions (safety, auth/upgrade gating) are **plain Python code that never calls a model** —
they cannot be prompt-injected or talked out of. Only the final "answer the question" step is
a model call, and even that model is restricted to a fixed **tool menu** rather than being
trusted to know prices, class times, or the caller's entitlements from the prompt alone.

```
START → safety_gate ─┬─(unsafe)→ finish (canned safety response)
                      └─(safe)──→ triage ─┬─(produced an answer)→ finish
                                           └─(needs the model)────→ respond → END
```

### 3.2 Node 1 — `safety_gate`

Pure keyword matching against `HIGH_RISK_TERMS` (chest pain, medication, self-harm, steroids,
etc.) and `INJURY_TERMS` (fracture, concussion, slipped disc...). If matched, the graph
**short-circuits before any model call** and returns a fixed `SAFETY_RESPONSE` that tells the
member to see a professional and offers a human trainer handoff (`needs_human_handoff=True`).
This is the one place safety is enforced deterministically instead of "hoping the prompt holds."

### 3.3 Node 2 — `triage`

Also pure code. Classifies the message into a **route** (`gym`, `yoga`, `mma`, `reception`,
`account`) using keyword tables (`YOGA_TERMS`, `MMA_TERMS`, `RECEPTION_TERMS`, `ACCOUNT_TERMS`).
Two hard permission checks happen here, before any model call:

- **Not signed in + asking about "my account"/signup** → returns a canned `LOGIN_PROMPT` or
  `SIGNUP_PROMPT` and sets `action` to `"login"`/`"signup"`. The frontend widget renders a
  real form; FitBot **never** collects a password in the chat transcript.
- **Signed in but package lacks `personalised_programme` + asking for "make me a plan"** →
  returns a canned `UPGRADE_PROMPT` instead of letting the model attempt to fabricate a
  personalised programme it has no entitlement to deliver.

If neither branch fires, `triage` just tags the route and falls through to `respond`.

### 3.4 Node 3 — `respond` (the only model call)

```python
result = get_llm().generate_with_tools(
    SYSTEM_PROMPT, prompt, FITBOT_TOOLS,
    lambda name, arguments: execute_fitbot_tool(name, arguments, ctx),
)
```

The system prompt tells the model it has tools and must **never invent** prices, times, or
locked-content access — it must call a tool. `build_prompt()` assembles a minimal per-turn
prompt: which desk (route), who is asking, their entitlements (only if the route needs it),
their fitness profile (only for coaching routes), the last 4 turns of history, and the
question. Nothing is stuffed into the prompt that the model could get from a tool call
instead — this both shrinks token cost and stops stale entitlement data from being invisibly
baked into a long-lived prompt.

### 3.5 FitBot's tool menu (`FITBOT_TOOLS` in `tools.py`)

| Tool | Purpose | Backing function |
|---|---|---|
| `get_pricing` | Live membership packages/prices | `gym_ops.pricing_text` → `front_desk.pricing` |
| `get_timetable` | Next-7-day class schedule | `gym_ops.timetable_text` → `front_desk.timetable` |
| `search_knowledge` | Hybrid + agentic RAG over admin-uploaded PDFs, filtered by package | `gym_ops.search_documents` (§4) |
| `check_entitlement` | The signed-in caller's package/quota/expiry | Returns `ctx.entitlements`, or forces `request_login` if signed out |
| `request_login` | Renders the in-chat sign-in form | Sets `ctx.action = "login"` |
| `request_signup` | Renders the in-chat join form | Sets `ctx.action = "signup"` |

`execute_fitbot_tool()` is a pure dispatcher: unknown tool names return an error **string**
(never raise), so a hallucinated tool name degrades gracefully instead of crashing the graph.
A `ToolContext` dataclass carries per-request state (db session, entitlements string,
`is_authenticated`, `allowed_disciplines`) and accumulates side effects (`sources`, `action`)
that the tool calls populate, which the graph reads back after the model finishes.

### 3.6 Tool-calling loop mechanics (`services/llm.py`)

`generate_with_tools()` runs up to `MAX_TOOL_ROUNDS = 4` rounds:

1. Send the system prompt + user prompt + tool declarations to the provider.
2. If the model returns tool calls, execute each one via the `execute` callback, append the
   tool's *string* result back into the conversation (as a `function_response` for Gemini, or a
   `role: "tool"` message for Groq), and loop.
3. If the model returns plain text with no tool calls, that is the final answer.
4. If 4 rounds pass without a final answer, return whatever text was last seen.

Both `GeminiProvider` and `GroqProvider` implement this loop against their respective wire
formats (Gemini's `FunctionDeclaration`/`Part.from_function_response`, Groq's OpenAI-style
`tool_calls`/`role: "tool"`), so the rest of the codebase (FitBot, orchestrator) is provider-
agnostic — it only ever calls `get_llm().generate_with_tools(...)`.

### 3.7 Provider fallback chain (`LLMChain`)

```python
LLMChain([GeminiProvider(), GroqProvider()])
```

- Tries Gemini first, then Groq, in order.
- A `ProviderUnavailable(exhausted=True)` (HTTP 429 / `RESOURCE_EXHAUSTED`) puts that provider
  in a **cooldown** (`llm_cooldown_seconds`, default 900s) so subsequent requests in that
  window skip straight past it instead of paying its timeout again.
- If every provider is unconfigured, returns a friendly "not configured" message instead of a
  stack trace. If every configured provider refuses, returns a friendly "try again" message.
- One `LLMChain` instance per process (`@lru_cache` on `get_llm()`), so the cooldown state is
  shared across all requests on that worker.

### 3.8 Safety/UX rules baked into the system prompt

- No diagnosis, medication advice, extreme dieting, or unsupervised sparring guidance.
- If a tool reports a discipline is `LOCKED` (see §4), answer generally and name the upgrade —
  never refuse outright, never quote gated documents.
- Never ask for a password/OTP/card number in the chat.
- Reply in the member's language, including Hindi/Hinglish.
- Only append a "Sources:" line when documents were actually used.

---

## 4. Advanced RAG (hybrid retrieve + agentic retry)

**File:** `backend/app/services/gym_ops.py::search_documents`

Naive RAG retrieves once and hopes the top-k chunks answer the question. Master GYM adds a
**grade-and-retry loop**, capped at `MAX_RETRIEVAL_ATTEMPTS = 2` (one retrieve + at most one
reformulated retry) so latency and cost stay bounded:

```python
def search_documents(db, query, discipline, allowed):
    shelf = discipline if discipline in KNOWN_DISCIPLINES else "gym"
    if shelf not in allowed:
        return "LOCKED: ...", []          # package filter — never widened by the retry loop

    search_query = query
    for attempt in range(MAX_RETRIEVAL_ATTEMPTS):
        chunks = retrieve_chunks(db, search_query, shelf, allowed)
        if not chunks or attempt == last:
            break
        enough, rewrite = grade_retrieval(query, chunks)   # LLM judge
        if enough or not rewrite:
            break
        search_query = rewrite                              # retry with the SAME shelf only
    return render(chunks), chunks
```

**The LLM judge** (`grade_retrieval`) is a *cheap, separate* model call with a strict JSON-only
system prompt:

```
{"enough": true, "rewrite": ""}
```

- `enough=true` → the retrieved passages can answer the question from the gym's own material.
- `enough=false` → `rewrite` is a short, improved query **for the same topic** — the judge is
  explicitly told it may never suggest a different sport/discipline and never invent a filename.
- If the judge's reply is unparseable JSON, `parse_retrieval_grade()` defaults to `enough=True`
  so a flaky judge call degrades to "use what we already retrieved" rather than looping.
- If no LLM provider is configured at all, grading is skipped entirely (`provider.is_configured`
  check) and the first retrieval result is used as-is.

**Package filtering is structural, not a prompt instruction.** `readable_disciplines()` computes
the caller's allowed shelves (always includes the public `reception` shelf) *before* any
retrieval happens, and `retrieve()` filters by discipline **inside the SQL query** — an excluded
shelf's chunks are never fetched, ranked, or seen by the grading model. A locked discipline
short-circuits to a `LOCKED:` string for the model to explain and upsell, with **zero calls**
to the vector store.

**Hybrid retrieve** (`services/rag.py::KnowledgeBase.retrieve`) runs two legs over the
same package-filtered shelf, then fuses them with Reciprocal Rank Fusion (RRF, `k=60`):

1. **Keyword** — token-overlap scoring on chunk text (exact terms, numbers, exercise names).
2. **Semantic** — `pgvector` `cosine_distance` / HNSW (`vector_cosine_ops`) on Gemini embeddings.

Chunks carry a `kind` (`text` | `table` | `image_summary` | `image_detail`) so the model knows
whether a hit came from prose, a preserved markdown table, or an image caption/detail.

**Ingest** (`services/pdf_extract.py` → `rag.ingest_pdf`): classify scanned vs text
(avg selectable chars/page < 40 → OCR). Direct path extracts text, PyMuPDF tables (row order
kept as markdown), and embedded images (Gemini writes both summary and detail). Scanned path
renders pages and OCRs with Gemini vision into the same kinded passages. Documents store
`ingest_mode` (`direct` | `ocr`).

---

## 5. Admin multi-agent orchestrator ("Copilot")

**File:** `backend/app/agents/orchestrator.py`. Admin-only, surfaced at
`POST /api/admin/copilot/ask` and in the Admin Insights "Copilot" tab.

### 5.1 Why a supervisor pattern

Two specialist agents already existed — `DataAgent` (`agents/analyst.py`, numbers only) and
`AdvisorAgent` (`agents/advisor.py`, recommendations only). Rather than merging their prompts
into one confusing mega-agent, the Copilot is a **third, thin LangGraph graph** that sits above
both and **delegates via tool calls** — the classic supervisor/router multi-agent pattern.

```
START → respond → END
```

Just one node, but that node's job is entirely about *choosing and combining* the two
specialists, never about answering directly from its own knowledge.

### 5.2 The two tools the supervisor can call

```python
ORCHESTRATOR_TOOLS = (
    ToolSpec("ask_data_analyst", ..., parameters={"question": str}),
    ToolSpec("get_advisor_report", ..., parameters={}),
)
```

- **`ask_data_analyst(question)`** → runs the entire `DataAgent` LangGraph
  (`agents/analyst.py`), which itself: (a) asks the model to pick 1–3 metric keys from a
  vetted registry, (b) runs only those registry functions in `services/analytics.py`
  (real SQL, never model-written SQL), (c) asks the model to narrate the resulting numbers.
  Returns narration text + raw `Metric` objects.
- **`get_advisor_report()`** → runs the entire `AdvisorAgent` LangGraph (`agents/advisor.py`),
  which computes rule-based `Recommendation`s in `services/insights.py` (deterministic —
  independent of whether any LLM is even reachable) and asks the model to write a short
  covering briefing using **only** those findings.

Both tools return **plain rendered text**, so the supervisor never has to parse structured
data back out of a sub-agent's output — it just weaves the text into one final answer.

### 5.3 Supervisor system prompt contract

```
- ask_data_analyst: ... Always call this for "how many / how much / which members / are
  classes full" questions.
- get_advisor_report: ... Call this for "what should I do / what needs attention / briefing".
- For compound questions ("why is revenue soft and what should I do?"), call BOTH tools.

Rules:
- Use only what the tools return. Never invent a number or a problem.
- Name which specialist(s) you used in one short closing line, e.g. "Sources: DataAgent, AdvisorAgent."
- Keep it under 280 words.
```

`OrchestratorContext` accumulates `agents_used`, `metrics`, and `recommendations` as the tools
run, so the API layer can return structured `MetricTable`/`RecommendationItem` payloads
alongside the prose answer (used by the frontend to render tables, not just text).

### 5.4 Fallback when no LLM is configured

`classify_intent()` is a **cheap keyword router** (`DATA_TERMS` vs `ADVICE_TERMS`) used by
`_keyword_fallback()` when `provider.is_configured` is `False`. It defaults to calling **both**
tools if intent is ambiguous — "safer than refusing" — and stitches the two texts together with
a manual `Sources:` line. This means the Copilot **never hard-fails** even with zero API keys
configured; it just loses the model's synthesis quality.

### 5.5 Multi-agent call graph in full

```
Admin question
     │
     ▼
Copilot supervisor (orchestrator.py)
     │
     ├──tool call──▶ ask_data_analyst ──▶ DataAgent LangGraph (analyst.py)
     │                                       │
     │                                       ├─ choose(): LLM picks metric keys (or keyword fallback)
     │                                       ├─ gather(): analytics.run_metrics() — real SQL only
     │                                       └─ narrate(): LLM explains the numbers
     │
     └──tool call──▶ get_advisor_report ──▶ AdvisorAgent LangGraph (advisor.py)
                                                │
                                                ├─ scan(): insights.build_recommendations() — pure rules
                                                └─ brief(): LLM writes the covering note
     │
     ▼
Copilot combines both texts into one briefing, appends "Sources: DataAgent, AdvisorAgent."
```

Three separate LangGraph state machines, one HTTP request. Every number that reaches the admin
traces back to a named SQL function in `analytics.py`; every recommendation traces back to a
named rule in `insights.py`. The LLM's role at every layer is **explain, never invent.**

---

## 6. Model Context Protocol (MCP) servers

Both servers are built on the official `mcp` Python SDK (`MCPServer` class, v2 API) and are
launched as separate processes (`python -m app.mcp_server` / `master-gym-mcp` console script).
They exist so any MCP-aware client (Cursor, Claude Desktop) can call the gym's real tools
directly — without going through the web app — while guaranteeing identical business logic to
FitBot and the web API, because **all three consume the same `gym_ops.py` functions.**

### 6.1 Public MCP server — `app/mcp_server.py`

No authentication. Read-mostly tools plus one write path with server-side entitlement checks:

| Tool | Notes |
|---|---|
| `get_pricing` / `get_timetable` | Same as FitBot's tools. |
| `search_knowledge(query, discipline)` | Staff-level MCP access reads every discipline shelf (`("gym","yoga","mma")` passed as `allowed`), still runs the agentic retry loop. |
| `list_metric_keys` / `get_gym_metrics(keys)` | Only registry keys execute — a comma-separated list of anything else is silently dropped, same guard as the admin API. |
| `list_upcoming_classes` | Returns class ids, seats left — needed before calling `book_class`. |
| `book_class(member_email, class_id)` | Re-runs the **exact same** entitlement, capacity and duplicate checks as the HTTP booking endpoint (`entitlements_for(...).may_book(...)`), so an MCP client cannot bypass package limits. |

### 6.2 Admin-only MCP server — `app/mcp_admin.py`

Exposes the **Copilot orchestrator** itself as an MCP tool, gated behind a real login flow
instead of a static credential, because MCP tool arguments are not an appropriate place to keep
resending a password:

```
1. admin_login(email, password)   → verifies against the DB, returns a short-lived session_token
2. ask_copilot(question, session_token) → re-checks role from the DB on every call
3. admin_logout(session_token)    → acknowledges; JWT expiry does the real work
```

**Token design (`core/security.py::create_mcp_admin_token`):**
- A JWT with `purpose: "mcp_admin"` and a 60-minute expiry, separate from the web app's
  `access_token` (different claim, so a web session token cannot be replayed here and vice
  versa).
- `_require_admin_session()` decodes the token, checks the `purpose` claim, then **re-reads the
  user from the database** and re-checks `role == ADMIN` and `active == True` on every single
  tool call — the token's existence is necessary but not sufficient; role is never trusted
  from the token payload alone, only the subject id is.
- Login failure uses **identical wording** for "unknown email" and "wrong password" to avoid
  account enumeration.

`ask_copilot()` invokes `orchestrator_workflow.invoke({"question": ..., "db": ...})` — the exact
same LangGraph used by the HTTP `/api/admin/copilot/ask` endpoint — and returns the answer plus
which specialist agents were used and the caller's email, for an audit trail in the MCP client's
transcript.

`sample_questions()` needs no auth and lists example prompts for both specialists, so an admin
using an MCP client is not left guessing what to ask.

**Deliberately not wired into any AI tool on this machine** per project requirements — the
module ships as reference code with explicit instructions in its docstring that it should only
be run on a machine the admin controls.

---

## 7. Data layer

**File:** `backend/app/db.py` — single SQLAlchemy 2.0 `Base` with typed `Mapped[...]` columns.

| Table | Purpose |
|---|---|
| `users` | One row per member/trainer/admin. Argon2 password hash, `Role` enum. |
| `membership_plans` | Sellable packages: `allowed_disciplines` (CSV), `monthly_class_quota` (`-1` = unlimited), `personalised_programme`, `priority_support`. |
| `memberships` | A purchased plan instance with `starts_on`/`expires_on`/`status`. |
| `fitness_profiles` | Goal, experience, injuries, equipment, assigned trainer — one row per member. |
| `programmes` | Trainer-written workout/diet plan text, tied to a member + trainer. |
| `class_schedules` / `class_bookings` | Timetable and seat bookings, unique-constrained so a member cannot double-book the same class. |
| `conversations` / `chat_messages` | FitBot transcript storage, including JSON-encoded source citations. |
| `knowledge_documents` / `knowledge_chunks` | Ingested PDFs (`ingest_mode`) and kinded passages (`text`/`table`/`image_*`) with embeddings (`Vector(768)`, `Text` under SQLite). |
| `audit_events` | Append-only log of sensitive admin actions (analyst queries, copilot queries, document uploads/deletes, knowledge changes). |

**Entitlements** (`services/entitlements.py`) are computed fresh on every request from the active
membership row — never cached, never inferred client-side. `may_book(discipline)` is the single
choke point that both the HTTP booking endpoint and the MCP `book_class` tool call, so package
rules cannot diverge between the two surfaces.

**Analytics** (`services/analytics.py`) is a **registry of named, parameterless SQL functions**
(`membership_overview`, `revenue_summary`, `signup_trend`, `expiring_soon`, `class_utilisation`,
`trainer_load`, `unassigned_members`, `missing_programmes`, `idle_members`,
`knowledge_coverage`, `fitbot_activity`). `run_metrics(db, keys)` only executes keys present in
`REGISTRY` — a model-hallucinated key is silently dropped rather than executed as arbitrary SQL.
This registry is the reason DataAgent (and the Copilot, transitively) can never write or run
free-form SQL.

**Insights** (`services/insights.py`) turns those same metrics into `Recommendation` objects via
plain Python `if` statements (renewal window, understaffed/overloaded trainers, empty timetable,
declining signups, etc.) — computed identically whether or not any LLM is reachable, which is
why AdvisorAgent still returns useful output with zero API keys configured.

---

## 8. API surface (FastAPI routers, all under `/api`)

| Router | File | Scope |
|---|---|---|
| `auth` | `api/auth.py` | Register (public, member-only), login, both rate-limited. |
| `membership` | `api/membership.py` | Plans, purchase, entitlements, class timetable, booking. |
| `people` | `api/people.py` | Member/trainer CRUD, fitness profiles, programmes — role-gated. |
| `fitbot` | `api/fitbot.py` | `/fitbot/chat` (rate-limited, works signed-out), conversation transcript retrieval. |
| `knowledge` | `api/knowledge.py` | Admin PDF upload/list/delete. Flow: validate → temp → SHA-256 dedup → scanned-vs-text classify → direct extract or vision OCR (text/table/image summary+detail) → embed → hybrid-ready `knowledge_chunks` + `ingest_mode` on `knowledge_documents` + audit. |
| `intelligence` | `api/intelligence.py` | Admin-only: `analyst/metrics`, `analyst/ask`, `advisor/report`, `copilot/ask`. |

**Auth model:** stateless JWT bearer tokens (`create_access_token`), role read straight from the
decoded payload for routing but **re-verified against the live DB row** wherever a permission
actually matters (e.g. `_guard_demo_account`, admin MCP). `require_roles(*roles)` in
`api/deps.py` is the single dependency factory behind `require_admin`/`require_staff`.

**Demo accounts:** three shared read-only logins (`*-demo@example.com`) let a visitor tour every
dashboard. `_guard_demo_account()` blocks any `POST/PUT/PATCH/DELETE` from those accounts except
an explicit allowlist (`/admin/analyst/ask`, `/admin/copilot/ask`, and any `/book` suffix) so the
tour can still *ask* the agents and book a class without leaving state that would surprise the
next visitor.

**Seeding (`scripts/seed.py` / `scripts/reset_db.py`):** `--public-demo` creates the three
read-only logins; `--demo` adds a small trainer/member/class set; `--rich-demo` builds a fuller
local dataset (3 trainers including an idle one, 8 members across Starter/Performance/Complete
plus lapsed and never-subscribed cases, a week of classes at varied fill, bookings, programmes —
including a Performance member with no programme so the Advisor can flag an unfulfilled promise).
Seeded rows persist in the configured DB across restarts; `reset_db` wipes schema + knowledge
chunks and optionally re-seeds.

**Rate limiting** (`core/rate_limit.py`): an in-process sliding-window counter keyed by
`(bucket, client_ip)` — `chat` (20/5min), `login` (10/5min), `register` (5/hour). No Redis
dependency; correct trade-off for a single free-tier instance.

---

## 9. Frontend architecture

**Stack:** React 18 + TypeScript + Vite + Tailwind CSS v4 (`@theme` tokens, no config file).

| File | Role |
|---|---|
| `src/components/Layout.tsx` | Shell: sticky nav, brand mark, footer, mounts `FitBotWidget` globally. |
| `src/components/FitBotWidget.tsx` | Floating chat widget available on every page, including signed-out. Renders in-chat login/signup forms when FitBot's `action` field asks for one — **never** a password field inline in the transcript. |
| `src/components/ui.tsx` | Design system primitives: `Button`/`ButtonLink`, `Badge`, `Field`, `Alert`, `Spinner`, `EmptyState`, `Stat`. |
| `src/pages/Landing.tsx` | Marketing homepage — hero, disciplines, FitBot explainer, CTA. |
| `src/pages/Packages.tsx` | Plan cards fetched live from `/api/plans`, purchase flow. |
| `src/pages/Login.tsx` / `Join.tsx` | Auth forms + one-click demo logins. |
| `src/pages/MemberDashboard.tsx` / `TrainerDashboard.tsx` / `AdminDashboard.tsx` | Role-specific consoles. |
| `src/pages/AdminInsights.tsx` | Tabs: **Data analyst**, **Advisor**, **Copilot** — the Copilot tab is the UI for the multi-agent orchestrator, with a single question textbox and clickable sample questions. |
| `src/context/AuthContext.tsx` | JWT storage, `signIn`/`signUp`/`signOut`, entitlement caching, `homeFor(role)` router helper. |
| `src/lib/api.ts` | Typed fetch client — one function per endpoint, typed request/response models mirroring `schemas.py`. |
| `src/lib/media.ts` | Central place for hero/discipline imagery URLs. |

**Design system:** dark charcoal (`ink-*` scale) base, warm off-white body text (`sand-*`), a
single lime "volt" accent reserved for calls-to-action and the `GYM` wordmark, `Bebas Neue`
display type paired with `Archivo` body type — deliberately editorial/premium rather than
generic SaaS-dashboard styling. `design-preview.html` is a static, dependency-free mirror of the
same visual language for quick design review outside the React build.

---

## 10. Testing

**Backend — 193 pytest tests** across:
- `test_workflow.py` — FitBot graph routing, safety gate, triage short-circuits.
- `test_tools.py` — every FitBot tool + `execute_fitbot_tool` dispatch + the public MCP server's
  tool registration.
- `test_agentic_rag.py` — retrieval grading, rewrite loop, max-attempt cap, locked-shelf short-circuit.
- `test_pdf_hybrid_rag.py` — scanned-vs-text detect, OCR structured split, table order, RRF fusion.
- `test_orchestrator.py` — intent classification, tool delegation, admin-only API access control.
- `test_mcp_admin.py` — login success/failure wording, token purpose/role re-checks, session expiry.
- `test_llm_chain.py` — provider fallback, cooldown behaviour, tool-calling round-trip with a fake tool provider.
- `test_front_desk.py`, `test_fitbot.py`, `test_knowledge_access.py` — end-to-end chat behaviour, package-based document locking.
- `test_analytics.py`, `test_intelligence.py`, `test_authorization.py`, `test_membership.py`, `test_auth.py`, `test_demo_accounts.py`, `test_rate_limit.py` — the rest of the HTTP surface.

**Frontend** — Playwright E2E (`frontend/e2e/insights.spec.ts` and friends) covering the Admin
Insights tabs including the Copilot tab and its sample questions.

**Lint:** Ruff (`select = ["E","W","F","I","B","UP","C4"]`) on the backend; `tsc --noEmit` on the
frontend.

---

## 11. Key design principles (why it's built this way)

1. **Permission decisions are code, not prompts.** Safety gating, login/signup gating, and
   package-based document locking all happen in deterministic Python before or around any model
   call — a jailbroken prompt cannot grant access it was never given.
2. **Numbers and documents come from tools, never from model memory.** Pricing, class times,
   metrics, and knowledge-base passages are always fetched live; the system prompts explicitly
   forbid inventing any of them.
3. **One shared operations layer (`gym_ops.py`)** — FitBot's tools, the public MCP server, and
   (transitively, via the orchestrator) the admin Copilot all call the same functions, so
   behaviour cannot silently diverge between "the chatbot," "the API," and "an MCP client."
4. **Agents are composed, not merged.** DataAgent and AdvisorAgent are single-purpose and
   independently testable; the Copilot adds a supervisor layer on top rather than growing either
   agent's prompt into an unmanageable do-everything system.
5. **Graceful degradation everywhere.** No API key configured → still functional (keyword
   routing, rule-based recommendations, direct SQL narration skipped but data still returned).
   One provider exhausted → automatic fallback with cooldown. Unparseable model output → safe
   default rather than a crash.
6. **The web app is never bypassed.** MCP tools and admin endpoints re-run the exact same
   entitlement/authorization checks as the browser-facing paths — there is no "backdoor" surface
   with looser rules.
