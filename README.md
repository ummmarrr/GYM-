# Master GYM

A gym management web app with **FitBot**, an AI coach that acts as the receptionist, gym
trainer, yoga coach or MMA coach depending on what you ask it. Built entirely on free tools.

Three roles, each with its own dashboard: **Admin**, **Trainer** and **Member**. What a member
can actually do is decided by the package they bought, and that is enforced on the server.

## What's inside

| Layer | Choice | Why |
| --- | --- | --- |
| Agent flow | LangGraph | The safety gate, triage and answering steps are explicit and testable |
| LLM | Gemini, falling back to Groq | Two free tiers in sequence outlast either one alone |
| Retrieval | pgvector + PyMuPDF | Embeddings sit beside the data, so one query filters and ranks |
| API | FastAPI + SQLAlchemy | SQLite locally, Postgres when hosted — same models either way |
| Auth | Argon2 password hashing + JWT | Argon2 is the current recommendation for passwords |
| Web app | React + Vite + Tailwind v4 | Fast dev loop, no UI library to fight |

## Project layout

```
U/
├── backend/          # FastAPI app, agent, tests — fully self-contained
│   ├── app/
│   │   ├── agents/       # LangGraph workflows: fitbot, analyst, advisor
│   │   ├── api/          # auth, membership, people, fitbot, knowledge, intelligence
│   │   ├── core/         # settings and security primitives
│   │   ├── services/     # llm, rag, entitlements, analytics, insights
│   │   ├── db.py         # SQLAlchemy models
│   │   └── schemas.py    # Pydantic request/response models
│   ├── scripts/seed.py   # creates the first admin
│   └── tests/            # 139 tests, no network calls
└── frontend/         # React app — fully self-contained
    ├── e2e/              # 45 Playwright browser tests
    └── src/
        ├── components/   # Layout, FitBotWidget, route guard, UI primitives
        ├── context/      # auth state
        ├── lib/          # typed API client
        └── pages/        # landing, packages, auth, three dashboards
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
- `GROQ_API_KEY` — optional but recommended, free and no card, from
  https://console.groq.com/keys. FitBot uses it when Gemini's daily quota runs out.

Create your admin account and some demo data:

```bash
python -m scripts.seed --admin-email you@example.com --admin-password "your-password" --demo
```

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
programmes, books and cancels classes within their quota, and edits the fitness profile that
FitBot reads before every answer.

**Trainer** — sees only the members assigned to them, writes workout and diet programmes for
those members, and manages the class timetable.

**Admin** — signs in through the web app only. Creates members and trainers, changes roles,
assigns trainers to members, activates or deactivates accounts, controls the knowledge base by
uploading and removing the PDFs FitBot is allowed to quote, and has the two analysis agents
described below.

## How FitBot behaves

1. **Safety first.** Anything about chest pain, injuries, medication or steroids is answered
   with a referral to a professional and flagged for a human trainer. The model is never
   called for these.
2. **Triage before spending a model call.** A signed-out visitor asking "when does my plan
   expire?" gets a secure sign-in form rendered inside the chat, not a guess. A member on a
   package without personalised programming gets an upgrade prompt.
3. **Answer facts from the database, not the model.** Prices and class timings live in
   `membership_plans` and `class_schedules`, so `app/services/front_desk.py` reads them
   directly. These are the most common questions a gym site gets, they cost no quota, and the
   answer is exact — the model is told never to invent a price, so it could not answer well
   anyway.
4. **Answer the rest with the gym's own documents.** Retrieval is scoped both to the
   discipline being asked about and to what the caller's package includes, and answers cite
   the source PDF and page.

FitBot never asks for a password. Signing in from the chat uses a real form that posts
straight to the API, so credentials never enter the conversation transcript.

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

Both keys are optional. With neither, FitBot explains that it needs one; with one, it uses it.

## The two admin agents

Both live at **Admin console → Insights**, and both are behind `require_admin`. Trainers and
members have no route to these figures.

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
signup growth.

## Tests

```bash
cd backend
python -m pytest
```

139 tests covering agent routing and safety logic, authentication, role boundaries, package
entitlements, the document access ladder, conversation privacy, metric correctness, the
analyst's key validation, provider fallback and the front-desk answers. The model is stubbed,
so the suite is fast, free and offline.

```bash
cd frontend
npm run lint      # TypeScript type check
npm run build     # production build
```

### Browser tests

45 Playwright tests drive a real Chromium against the running app: the public site, signup and
login, route guards for all three roles, the member dashboard, class booking and entitlement
refusals, the trainer desk, the admin console, PDF ingestion, both admin agents, and the FitBot
widget. They also fail the run on any console error or 5xx response.

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
- **SQLite has no migrations here.** Tables are created on startup. If you change a model,
  delete `backend/gym_coach.db` and re-run the seed script, or add Alembic.
- **Admin accounts are created from the server only**, via `scripts/seed.py` or by an existing
  admin. Self-signup always produces a member, whatever the request body says.
