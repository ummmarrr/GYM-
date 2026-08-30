# Master GYM

A gym management web app with **FitBot**, an AI coach that acts as the receptionist, gym
trainer, yoga coach or MMA coach depending on what you ask it. Built entirely on free tools.

Four roles, each with a purpose-built surface: **Admin**, **Reception**, **Trainer** and
**Member**. What a member can actually do is decided by the package they bought, and that is
enforced on the server.

Reception runs the tablet-friendly **Front desk** at `/front-desk`: it scans a secure member QR
in the browser, shows the member photo and live package/class/trainer/notices briefing, then
records attendance only after a human confirms the match.

## What's inside

| Layer | Choice | Why |
| --- | --- | --- |
| Agent flow | LangGraph | Safety and auth stay as code branches; the rest is tool-calling |
| Tools / MCP | Shared `gym_ops` + two MCP servers | FitBot and Cursor clients call the same operations |
| LLM | Gemini, falling back to Groq | Two free tiers in sequence outlast either one alone |
| PDF ingest | PyMuPDF + Gemini vision OCR | Text PDFs extract directly; scanned PDFs are OCR'd |
| Retrieval | Hybrid (keyword + semantic RRF) + agentic retry | Exact terms and meaning both matter; weak hits get one rewrite |
| Admin AI | Copilot over DataAgent + AdvisorAgent | One textbox; supervisor routes to specialists |
| Door check-in | ZXing in-browser QR + signed passes | Camera stays on the tablet; API gets only a token |
| API | FastAPI + SQLAlchemy | SQLite locally, Postgres when hosted — same models either way |
| Auth | Argon2 password hashing + JWT | Argon2 is the current recommendation for passwords |
| Web app | React + Vite + Tailwind v4 | Premium dark UI; fast dev loop |

## Docs map

| Doc | What it covers |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Deep dive: FitBot, hybrid/agentic RAG, Copilot, MCP, data model |
| [backend/BACKEND.md](backend/BACKEND.md) | API, services, seed flags, knowledge ingest steps |
| [frontend/FRONTEND.md](frontend/FRONTEND.md) | Pages, components, API client, E2E notes |
| [EXPLANATION.md](EXPLANATION.md) | Design decisions and interview / resume storytelling |
| [DEPLOYMENT.md](DEPLOYMENT.md) / [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Hosting on Render, Cloudflare Pages, Neon |

## Project layout

```
GYM-/
├── ARCHITECTURE.md
├── backend/              # FastAPI app, agents, MCP servers, tests
│   ├── app/
│   │   ├── agents/       # FitBot, DataAgent, AdvisorAgent, Copilot orchestrator
│   │   ├── api/          # auth, membership, people, front_desk, fitbot, knowledge, intelligence
│   │   ├── core/         # settings and security primitives
│   │   ├── services/     # llm, pdf_extract, rag (hybrid), gym_ops, entitlements, analytics
│   │   ├── mcp_server.py # public gym tools for any MCP client
│   │   ├── mcp_admin.py  # admin-only Copilot MCP (login → session token)
│   │   ├── db.py
│   │   └── schemas.py
│   ├── scripts/
│   │   ├── seed.py       # --demo / --public-demo / --rich-demo
│   │   └── reset_db.py   # drop schema + optional re-seed
│   └── tests/            # 207 tests, no network calls
└── frontend/
    ├── e2e/              # 46 Playwright browser tests
    ├── design-preview.html
    └── src/
        ├── components/
        ├── context/
        ├── lib/          # api client, media URLs
        └── pages/        # landing, auth, dashboards, Front desk, Insights
```

## Setting up on a new machine

Requires **Python 3.11+** and **Node 20+**. Nothing else, and nothing paid.

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS or Linux: source .venv/bin/activate
pip install -e ".[dev]"

copy .env.example .env          # macOS or Linux: cp .env.example .env
```

Then edit `backend/.env`:

- `JWT_SECRET` — generate one with
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`
- `GEMINI_API_KEY` — free key from https://aistudio.google.com/apikey
  (needed for embeddings, FitBot answers, scanned-PDF OCR, and image captions)
- `GROQ_API_KEY` — optional but recommended, free and no card, from
  https://console.groq.com/keys. FitBot uses it when Gemini's daily quota runs out.

Create your admin account and some demo data:

```bash
python -m scripts.seed --admin-email you@example.com --admin-password "your-password" --demo
```

For a fuller local dataset (multiple trainers/members, all packages, classes, bookings,
programmes — useful for testing analytics and the admin Copilot):

```bash
python -m scripts.seed --rich-demo
# or wipe and rebuild everything:
python -m scripts.reset_db --yes --admin-email admin@example.com --admin-password "AdminPass123" --public-demo --rich-demo
```

| Seed flag | What you get |
| --- | --- |
| `--demo` | One trainer, one member (Performance), three classes |
| `--public-demo` | The three read-only logins on the sign-in page |
| `--rich-demo` | 3 trainers (one idle), 8 members across every package (plus lapsed / no package), a week of classes at varied fill, bookings, programmes |

Seed data lives in the database from `.env` (default local SQLite `backend/gym_coach.db`).
It survives PC restarts; it is cleared only by `reset_db`, deleting the DB, or changing
`DATABASE_URL`.

Shared read-only logins (`python -m scripts.seed --public-demo`):

| Role | Email | Password |
| --- | --- | --- |
| Member | member-demo@example.com | DemoMember123 |
| Trainer | trainer-demo@example.com | DemoTrainer123 |
| Admin | admin-demo@example.com | DemoAdmin123 |

Their passwords are printed on the sign-in page, so the API rejects writes from those
addresses (`demo_account_emails` in `app/core/config.py`). Asking the data/Copilot agents and
booking a class are the exceptions, since neither outlasts the visit in a harmful way.

Run the API:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://127.0.0.1:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to port 8000, so there are no URLs
to edit and no CORS setup to do.

### 3. Going live

The API runs on Render, the site on Cloudflare Pages and the database on Neon, all free.
[DEPLOYMENT.md](DEPLOYMENT.md) has the full walkthrough, the environment variables each host
needs, and what to do when the schema changes.

## How the roles differ

**Member** — sees their package and days remaining, their trainer-written workout and diet
programmes, books and cancels classes within their quota, edits the fitness profile that FitBot
reads before every answer, and shows a **My gym pass** QR on the dashboard for the door tablet.

**Reception** — lands on the dedicated check-in kiosk at `/front-desk`. It scans member passes,
verifies the person against the enrolled photo, records attendance, and sees only the
package / class / trainer / notices context needed at the door. Reception cannot open trainer
or admin tools (no Insights, no PDF knowledge, no role changes).

**Trainer** — sees only the members assigned to them, writes workout and diet programmes for
those members, and manages the class timetable.

**Admin** — signs in through the web app only. Creates members, trainers and reception staff,
changes roles, assigns trainers, activates or deactivates accounts, enrolls check-in photos,
rotates lost passes, publishes repair/closure notices, controls the knowledge base by uploading
and removing the PDFs FitBot is allowed to quote, can open the front-desk kiosk, and has the
Insights agents described below (DataAgent, AdvisorAgent, and the Copilot that orchestrates
both).

## Front desk check-in

A permanent tablet stays signed in as reception (or admin). Members show the QR from
**My gym pass**. Flow:

1. **Scan** — `@zxing/browser` reads the QR in the camera; only the opaque token is POSTed.
2. **Briefing** — server returns name, enrolled photo, package expiry, class quota, upcoming
   bookings, assigned trainer, active gym notices and last check-in (all from SQL).
3. **Confirm** — reception compares the person to the photo and taps Confirm or Reject.
4. **Attendance** — a row is written with method `qr` or `manual`. Repeats within four hours
   return the existing check-in (idempotent). Expired memberships still show a red warning but
   can be checked in so the visit is recorded.

Manual name / email / phone search covers forgotten phones. Pass tokens are HMAC-signed and
stored only as SHA-256 digests; rotating a pass revokes the old QR immediately. Camera frames
never leave the tablet and never call an LLM.

## How FitBot behaves

1. **Safety first.** Anything about chest pain, injuries, medication or steroids is answered
   with a referral to a professional and flagged for a human trainer. The model is never
   called for these.
2. **Triage before spending a model call.** A signed-out visitor asking "when does my plan
   expire?" gets a secure sign-in form rendered inside the chat, not a guess. A member on a
   package without personalised programming gets an upgrade prompt.
3. **Tool-calling agent for everything else.** After triage, the model picks tools:
   `get_pricing`, `get_timetable`, `search_knowledge`, `check_entitlement`, `request_login`,
   `request_signup`. Prices and timings still come from the database via those tools — the
   model never invents them.
4. **Advanced RAG on documents.** `search_knowledge` uses hybrid retrieve (keyword + semantic
   RRF) with an agentic grade-and-retry loop, still filtered by the caller's package in SQL.
   If the first pass looks weak, a small judge may rewrite the query and retrieve **once more
   on the same shelf** (max 2 attempts). Locked disciplines never enter that loop.
5. **Stream to the browser.** FitBot uses `/api/fitbot/chat/stream` (SSE: `meta`, `token`,
   `done`). Admin Insights does the same for analyst, advisor briefing and Copilot. The JSON
   endpoints remain as fallbacks. No extra streaming vendor or bill — same Gemini/Groq keys.

FitBot never asks for a password. Signing in from the chat uses a real form that posts
straight to the API, so credentials never enter the conversation transcript.

### Knowledge base (PDF ingest)

Admins upload PDFs under **Admin console → knowledge**. Each file is tagged with a discipline
(`gym` | `yoga` | `mma` | `reception`).

1. **Classify** — enough selectable text → direct extract; almost none → treat as scanned.
2. **Direct** — extract text (chunked), tables as markdown (row order kept), embedded images
   as both a short **summary** and a longer **detail** (via Gemini vision).
3. **Scanned** — render pages → Gemini vision OCR → same kinds of passages (text / table /
   image summary + detail). Needs `GEMINI_API_KEY`.
4. Embed and store chunks with a `kind`, plus `ingest_mode` (`direct` | `ocr`) on the document.

### Who FitBot may quote what to

Admins alone upload, list and delete PDFs. Everyone *reads* them indirectly, through FitBot's
answers, but how much they can reach climbs with the package:

| Caller | Documents in reach |
| --- | --- |
| Visitor, or a member with no active package | reception |
| Starter | reception, gym |
| Performance | reception, gym, yoga |
| Complete | reception, gym, yoga, mma |
| Trainer and admin | everything |

The ladder is not a second list to maintain: it reads `allowed_disciplines` off the package
the member actually bought, the same column that decides which classes they may book. Selling
a tier and unlocking its material therefore cannot drift apart. Filtering happens in the SQL
`WHERE` clause rather than after ranking, so an excluded document cannot shape an answer even
slightly. Ask about something your package excludes and FitBot still answers from general
knowledge, then names the package that unlocks the gym's own material.

### Surviving the free tier

Free LLM quotas are small, and a chatbot that stops working at lunchtime is not a product.
Three things keep FitBot answering:

- **Two providers, in order.** `app/services/llm.py` tries Gemini and falls through to Groq on
  failure, so the daily ceiling is the sum of both rather than the smaller one. Groq's
  `llama-3.1-8b-instant` allows 14,400 requests a day free.
- **A cooldown on exhausted providers.** Once a provider reports its quota is gone it is
  skipped for `LLM_COOLDOWN_SECONDS`. Without this, every later request would wait out that
  provider's timeout before falling through, and the chat would crawl.
- **A prompt budget.** Retrieved chunks and conversation history are both clipped, and fields
  the route cannot use are left out, which cut a typical call from about 2,500 tokens to 740.
  Output is capped too, since it counts against the same quota.

Both keys are optional for basic chat. With neither, FitBot explains that it needs one. Scanned
PDF OCR and image captions specifically need Gemini.

## The admin agents (Insights)

All live at **Admin console → Insights**, and all are behind `require_admin`. Trainers and
members have no route to these figures. Each agent's prose streams into the UI over SSE after
its tools/rules finish; metric tables and recommendation cards arrive on the final `done`
event.

**Copilot (orchestrator)** — one textbox. A supervisor routes the question to DataAgent,
AdvisorAgent, or both, then combines the answer. Sample prompts are labeled Data / Advice /
Both so admins know what to ask.

**DataAgent (data analyst)** — ask questions about the gym in plain English: "how much revenue
have we made?", "which members are at risk of leaving?". It answers with real numbers and shows
the tables it read.

**AdvisorAgent (recommendations)** — reviews the gym and returns prioritised recommendations,
each with the evidence that triggered it, the action to take and why it matters, plus a short
written briefing.

### Why they don't write SQL

The obvious build is text-to-SQL. This project deliberately does not do that, for two reasons.
An LLM with SQL access to this database could read `users.password_hash` or members' private
chat transcripts, and a hallucinated join produces a confident wrong number that looks just as
authoritative as a correct one.

Instead there is a registry of vetted queries in `app/services/analytics.py`. The agent chooses
metric *keys* from that registry; anything not in it is discarded before execution, so a
hallucinated key like `drop_all_users` simply does nothing. Every figure is computed by real
SQLAlchemy queries in our own code, and the model's only job is to explain them.

The recommendation rules in `app/services/insights.py` work the same way. Findings are computed,
not generated — if the Gemini key is missing or the API is down, you still get the full
prioritised list, just without the written briefing.

Current checks include renewals due, unfulfilled programme promises (members paying for a
trainer-written plan who never received one), members who stopped booking, under- and
over-subscribed classes, trainer overload and idle trainers, knowledge base gaps, and stalled
signup growth. `--rich-demo` seeds data that exercises several of these signals.

## MCP servers (local AI tools on your machine)

Two stdio MCP servers ship with the backend. Wire them only on a machine you control — not on
a shared PC.

| Entry | Command | Audience |
| --- | --- | --- |
| Gym tools | `python -m app.mcp_server` | Pricing, timetable, hybrid RAG, metrics, book class |
| Admin Copilot | `python -m app.mcp_admin` | Admin login → session token → `ask_copilot` |

Admin MCP auth: call `admin_login(email, password)` once; pass the returned `session_token` to
`ask_copilot`. Never put the password on every question. Role is re-checked from the database
on each call. See [backend/BACKEND.md](backend/BACKEND.md) for Cursor config examples.

## Tests

```bash
cd backend
python -m pytest
```

207 tests covering agent routing and safety logic, FitBot tools, FitBot and Insights SSE delivery, PDF classify / OCR split /
hybrid RRF, agentic RAG, the Copilot orchestrator, MCP admin auth, authentication, role
boundaries, secure/revocable member passes, attendance cooldowns, photo access, operational
notices, package entitlements, the document access ladder, conversation privacy, metric
correctness, provider fallback and FitBot front-desk answers. The model is stubbed, so the
suite is fast, free and offline.

```bash
cd frontend
npm run lint      # TypeScript type check
npm run build     # production build
```

### Browser tests

46 Playwright tests drive a real Chromium against the running app: the public site, signup and
login, route guards for member / trainer / admin, the member dashboard, class booking and
entitlement refusals, the trainer desk, the admin console, PDF ingestion, Insights (Copilot /
analyst / advisor), and the FitBot widget. Front-desk QR check-in is covered by backend
`test_attendance.py`; browser coverage for the kiosk can be added next. They also fail the run
on any console error or 5xx response.

Start both servers first, then:

```bash
cd frontend
npm run e2e          # run the suite
npm run e2e:report   # open the HTML report
```

Run these with a single worker, which is the default. SQLite serialises writes, so parallel
workers queue behind each other and time out rather than revealing real faults.

The admin specs sign in as a real account, so its credentials come from the environment rather
than the repository:

```powershell
$env:E2E_ADMIN_EMAIL = "you@example.com"
$env:E2E_ADMIN_PASSWORD = "your-admin-password"
```

## Notes on this build

- **Payments are simulated.** Choosing a package activates it immediately. No card details
  are collected anywhere. Swap `purchase_membership` in `app/api/membership.py` for a payment
  provider callback before charging anyone.
- **SQLite has no migrations here.** Tables are created on startup; a few knowledge columns
  are `ALTER`ed if missing, and hosted Postgres gets `ALTER TYPE role ADD VALUE IF NOT EXISTS
  'RECEPTION'` for the desk role. After a model change, prefer
  `python -m scripts.reset_db --yes ...` (or delete `backend/gym_coach.db` and re-seed), or
  add Alembic before you have real members.
- **Admin and reception accounts are created by an admin** (or `scripts/seed.py` for admin).
  Self-signup always produces a member, whatever the request body says.
- **Check-in is QR + human photo verification**, not face recognition. Photos live in Postgres
  (Render's disk is ephemeral). The kiosk needs HTTPS (or localhost) for the camera API.
- **Vector search needs Postgres + pgvector** when hosted. Local SQLite still stores chunks for
  ingest tests; hybrid keyword ranking works locally, full semantic ranking is for Neon.
