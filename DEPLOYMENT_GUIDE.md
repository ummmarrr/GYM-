# Deployment A to Z

The complete reference for running Master GYM in production: the big picture first, then every
setting, then every click, then how to operate it once it is live.

If you just want the original walkthrough of how this project went live, that is
[DEPLOYMENT.md](DEPLOYMENT.md). This document is the fuller version — it adds the architecture
reasoning, a complete environment variable reference, the cost and billing safety rules,
operations, key rotation, backups, and how to take it down cleanly.

Read Part 1 to understand it. Read Part 3 to do it. Read Part 7 before you put the link on your
resume.

---

# Part 1 — The high level

## 1.1 What "deployed" means here

Three separate services, each doing one job:

| Piece | Host | What it is |
| --- | --- | --- |
| React app | Cloudflare Pages | Static HTML, CSS and JS on a CDN |
| FastAPI app | Render | A Python process behind an HTTPS URL |
| Postgres + pgvector | Neon | The only thing that stores state |

Nothing else. No Redis, no separate vector database, no object storage, no queue.

## 1.2 The picture

```mermaid
flowchart TB
    U[Visitor's browser]

    subgraph CF[Cloudflare Pages - free]
        S[Static React bundle<br/>_redirects for SPA routing]
    end

    subgraph RN[Render - free web service]
        A[FastAPI + Uvicorn<br/>LangGraph agents<br/>Sleeps after 15 min idle]
    end

    subgraph NE[Neon - free Postgres]
        D[(16 tables<br/>+ pgvector embeddings)]
    end

    subgraph EX[External APIs]
        G[Gemini<br/>text + embeddings]
        Q[Groq<br/>backup text]
    end

    U -->|1. GET the site| S
    U -->|2. JSON + Bearer token| A
    A -->|3. SQL| D
    A -->|4. only when needed| G
    G -.->|out of quota| Q
```

The two arrows worth noticing:

- **Step 2 goes straight to Render, not through Cloudflare.** The CDN only serves files. It is
  not a proxy or a gateway. That is why CORS matters here and why the frontend needs to be told
  the API's address at build time.
- **Step 4 is dotted for a reason.** Most requests never reach an LLM. Prices, timetables, the
  safety gate, login prompts and every dashboard are answered without one.

## 1.3 What happens on a real page load

1. Browser asks Cloudflare for `https://master-gym.pages.dev`. The CDN returns
   `index.html` plus hashed JS and CSS from the nearest edge location. Fast, always.
2. React boots. `AuthProvider` checks `localStorage` for a token. No token means **no API call
   at all**, so a visitor who only reads the landing page never touches Render.
3. The packages page needs data, so it calls `GET https://master-gym-api.onrender.com/api/plans`.
4. If Render has been idle 15 minutes, this request wakes it. That takes roughly 50 seconds.
   After 3 seconds the UI shows the "waking the demo server" banner.
5. Render's FastAPI process queries Neon. If Neon was also asleep, `pool_pre_ping` quietly
   replaces the dead connection instead of erroring.
6. JSON comes back. The browser checks the `Access-Control-Allow-Origin` header against the page
   origin. If `FRONTEND_ORIGIN` on Render does not list the Pages URL, the browser throws the
   response away and you see a CORS error in the console.

Steps 4 and 6 are where essentially every deployment problem lives.

## 1.4 Why this split

**Why static hosting for the frontend?** The React build is just files. Putting them on a CDN
means the site loads instantly worldwide, costs nothing, and cannot go down when the API does.
A visitor gets a working page even while Render is waking up.

**Why a separate API host?** The backend needs a live Python process for LangGraph and
SQLAlchemy. That is a different kind of thing from a static file, and Render is built for it.

**Why managed Postgres instead of the database on the API host?** This is the important one.
**Render's filesystem is ephemeral.** Anything written to disk is gone on the next deploy and
every time the free instance wakes from sleep. The project originally used SQLite (a file) and
ChromaDB (a folder), so every deploy would have wiped every member and every uploaded PDF.

Moving the data to Neon and the vectors into pgvector inside that same database means **nothing
the app cares about lives on disk**, so a disposable filesystem stops being a problem. That
migration is the single most important deployment decision in the project.

**Why pgvector rather than a hosted vector database?** Because the embeddings need to be
filtered by membership tier at query time:

```sql
WHERE discipline IN ('reception', 'gym')
ORDER BY embedding <=> :query_vector
LIMIT 3
```

One query filters and ranks. With a separate vector service you would either fetch and filter
afterwards — which lets excluded documents affect the ranking — or duplicate permission data
into the vector store and keep it in sync. It is also one fewer service and one fewer free tier
to manage.

---

# Part 2 — The mid level

## 2.1 What you need before starting

| Account | Cost | Card needed |
| --- | --- | --- |
| GitHub | Free | No |
| Render | Free | **No** |
| Cloudflare | Free | **No** |
| Neon | Free | **No** |
| Google AI Studio (Gemini key) | Free tier | **No** |
| Groq | Free | **No** |

Not one of these requires a payment method. That is not a coincidence — see Part 7.

Values to have ready:

| Value | Where it comes from |
| --- | --- |
| `DATABASE_URL` | Neon dashboard → Connection string → **the pooled one** |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `GROQ_API_KEY` | https://console.groq.com/keys |

## 2.2 The five code changes deployment required

Worth knowing because these are the things that break if you fork the project.

**1. The frontend can be told where the API is.** In development Vite proxies `/api` to
`127.0.0.1:8000`, so the browser sees one origin. In production the site and API are on
different domains, so relative URLs break.

```ts
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
const response = await fetch(`${API_BASE}/api${path}`, { ... });
```

There is exactly one `fetch` in the whole frontend, so this one line covers every call. Empty
by default, which preserves local proxy behaviour exactly.

**2. CORS accepts more than one origin.** `FRONTEND_ORIGIN` is read as a comma-separated list:

```python
@property
def allowed_origins(self) -> list[str]:
    return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]
```

**3. Client-side routing survives a refresh.** React Router owns `/login` and `/dashboard`, but
no such files exist on disk, so the CDN would return 404 on refresh. `frontend/public/_redirects`:

```
/*  /index.html  200
```

Vite copies `public/` into `dist/`, so it ships with every build.

**4. Per-caller rate limits.** On a public URL one loop could drain both LLM quotas and fill the
database with chat rows. `backend/app/core/rate_limit.py` caps 20 chat messages and 10 logins
per 5 minutes and 5 signups per hour, per caller, returning 429 with `Retry-After`. Behind
Render's proxy the socket address belongs to the proxy, so the caller is taken from the first
entry of `X-Forwarded-For`.

**5. A Render blueprint.** `render.yaml` describes the service so Render configures itself.

## 2.3 Complete environment variable reference

### On Render (the backend)

| Variable | Value | Set by | Notes |
| --- | --- | --- | --- |
| `PYTHON_VERSION` | `3.14.3` | `render.yaml` | |
| `ENVIRONMENT` | `production` | `render.yaml` | |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | `render.yaml` | Cheaper and faster than the default |
| `DISPLAY_TIMEZONE` | `Asia/Kolkata` | `render.yaml` | Used when printing class times |
| `JWT_SECRET` | generated | Render, once | Changing it signs everyone out |
| `DATABASE_URL` | Neon pooled string | **you** | `postgresql://` is rewritten automatically |
| `GEMINI_API_KEY` | your key | **you** | Optional but wanted |
| `GROQ_API_KEY` | your key | **you** | Optional, the fallback |
| `FRONTEND_ORIGIN` | your Pages URL | **you** | Comma-separated, scheme included, no trailing slash |

The four marked `sync: false` in `render.yaml` are deliberately not in git. Render asks for them
once in the dashboard.

Optional overrides, all of which have working defaults in `app/core/config.py`:
`ACCESS_TOKEN_EXPIRE_MINUTES` (480), `LLM_COOLDOWN_SECONDS` (900), `LLM_MAX_OUTPUT_TOKENS`
(500), `CHAT_RATE_LIMIT` (20), `RATE_LIMIT_ENABLED` (true), `DEMO_ACCOUNT_EMAILS`.

### On Cloudflare Pages (the frontend)

| Variable | Value | Notes |
| --- | --- | --- |
| `VITE_API_URL` | `https://master-gym-api.onrender.com` | **No trailing slash** |

One variable, and one trap: **it is baked into the JavaScript at build time, not read at
runtime.** Editing it in the dashboard changes nothing until you trigger a new deployment.

## 2.4 Build and start commands

| Service | Build | Run |
| --- | --- | --- |
| Render | `pip install --upgrade pip && pip install .` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Cloudflare | `npm run build` (= `tsc -b && vite build`) | static, output `dist` |

Two details. Render must bind `0.0.0.0` and use `$PORT`, not a hard-coded port, or the health
check never passes. And the frontend build type-checks first, so a TypeScript error fails the
deploy rather than shipping.

## 2.5 What lives where

| Data | Where | Survives a redeploy? |
| --- | --- | --- |
| Users, memberships, classes, bookings, programmes | Neon | Yes |
| Chat transcripts | Neon | Yes |
| PDF text chunks and embeddings | Neon (`knowledge_chunks`) | Yes |
| The uploaded PDF file itself | Nowhere — discarded after ingestion | N/A |
| JWT signing secret | Render env var | Yes, unless regenerated |
| Rate limit counters | Render process memory | **No** — reset on every restart |
| Built frontend assets | Cloudflare | Rebuilt each deploy |

Two consequences. The original PDF is not kept, only its extracted chunks, so there is nothing
to serve back to a user and nothing to lose. And rate limit counters reset when Render sleeps or
redeploys, which is acceptable for abuse protection and would not be for anything billing-related.

---

# Part 3 — The low level, step by step

## Step 0 — Pre-flight secrets audit

Do this before the first push. It is the only step that is hard to undo.

```powershell
# 1. Is .env ignored?
git check-ignore -v backend\.env

# 2. Is any .env tracked right now?
git ls-files | Select-String "\.env"

# 3. Was one ever committed, in any branch, at any point in history?
git log --all --name-only --pretty=format: -- "*.env" | Sort-Object -Unique
```

You want: check 1 confirms the ignore rule, check 2 shows **only** `backend/.env.example` and
`frontend/.env.example`, and check 3 prints nothing.

If check 3 prints anything, the key is in history and is burnt even if you delete the file now.
Rotate that key immediately, then clean history or start a fresh repository.

## Step 1 — GitHub

Both hosts deploy from Git.

```powershell
git init
git add -A
git commit -m "Master GYM: gym platform with the FitBot assistant"
git branch -M main
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

Public or private both work. Public is fine **only because** no secrets are committed — and for
a resume project, public is the point, since a recruiter should be able to read the code.

## Step 2 — Neon (the database)

1. Create a project at https://console.neon.tech. Pick a region near where the API will run.
   This project uses `ap-southeast-1` (Singapore).
2. Copy the **pooled** connection string. It looks like
   `postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/dbname?sslmode=require`.
   Pooled matters: Neon suspends idle databases, and the pooler handles reconnection much better.
3. Do nothing else. You do not need to create tables or enable the `vector` extension by hand.
   On first boot the app's lifespan hook runs `initialize_database()`, which enables `vector`,
   creates all sixteen tables, builds the HNSW index and seeds the three packages.

The front-desk release also adds the `RECEPTION` value to the existing Postgres `role` enum at
startup before reception accounts are created. New attendance/pass/photo/notice tables are
created by the same `create_all` step; no photo is stored on Render's ephemeral disk.

Region choice is not cosmetic. Every request makes several round trips to the database, so an
API in Singapore with a database in Virginia adds latency to every single call.

## Step 3 — Render (the backend)

1. Sign in to https://dashboard.render.com with GitHub.
2. **New → Blueprint**, select the repository. Render reads `render.yaml` and proposes a service
   called `master-gym-api`.
3. It prompts for the four `sync: false` values. Paste them:
   - `DATABASE_URL` — the Neon pooled string, exactly as given. No editing; the app rewrites
     `postgresql://` to `postgresql+psycopg://` itself.
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
   - `FRONTEND_ORIGIN` — you do not have the Pages URL yet. Put `http://localhost:5173` and fix
     it in Step 5.
4. **Apply.** The first build takes three to five minutes, mostly compiling dependencies.
5. Confirm it is alive:

```powershell
curl https://master-gym-api.onrender.com/api/health
```

Expected:

```json
{"status": "ok", "app": "Master GYM", "bot": "FitBot"}
```

That single response proves a lot at once: the build succeeded, Uvicorn bound the right port,
and the app imported cleanly. It does **not** prove the database works — check the logs for the
startup line, or call `/api/plans`, which returns the three seeded packages and therefore proves
Neon is connected.

## Step 4 — Cloudflare Pages (the frontend)

1. https://dash.cloudflare.com → **Workers & Pages → Create → Pages → Connect to Git**.
2. Same repository, then:

| Setting | Value |
| --- | --- |
| Framework preset | Vite |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Root directory | `frontend` |

3. Environment variables → add `VITE_API_URL` = your Render URL, **no trailing slash**.
4. Deploy. You get something like `https://master-gym.pages.dev`.

Root directory is the setting people miss. Without it Cloudflare builds from the repo root, finds
no `package.json`, and fails.

## Step 5 — Introduce them to each other

The browser will refuse to use API responses until the backend names the site as an allowed
origin. In Render → your service → **Environment**, set:

```
FRONTEND_ORIGIN = https://master-gym.pages.dev
```

Keep localhost too if you want to develop against production data:

```
FRONTEND_ORIGIN = https://master-gym.pages.dev,http://localhost:5173
```

Save. Render restarts automatically. Scheme included, no trailing slash, no spaces.

## Step 6 — Create the first admin

The database has packages but no people. Admins cannot be created from the browser by design, so
run the seed script from your machine against the production database:

```powershell
cd backend
$env:DATABASE_URL = "<your Neon pooled connection string>"
..\.venv\Scripts\python.exe -m scripts.seed --admin-email you@example.com --admin-password "a-strong-password"
```

Then, for the shared read-only logins the sign-in page advertises:

```powershell
..\.venv\Scripts\python.exe -m scripts.seed --public-demo
```

For local testing with a denser dataset (multiple trainers/members, all packages, classes,
bookings, programmes), add `--rich-demo` on seed or on `reset_db`. That data lives in the DB
and survives restarts until you reset or change `DATABASE_URL`.

That creates `member-demo@`, `trainer-demo@` and `admin-demo@example.com` with the passwords
printed on the sign-in page. Because those passwords are public, the API refuses every write
from those three addresses — the list is `demo_account_emails` in `app/core/config.py`, and the
guard lives in `get_current_user`, so it covers every write endpoint automatically. Asking the
data agent and booking a class stay open, since neither outlives the visit.

Remember to clear `$env:DATABASE_URL` from your shell afterwards so later local commands do not
silently hit production.

## Step 7 — Verify, in this order

Each step exercises a different layer, so the first failure tells you where the problem is.

| # | Do this | Proves |
| --- | --- | --- |
| 1 | Open the site | Cloudflare is serving the build |
| 2 | The packages page shows three plans | CORS is right, `VITE_API_URL` is right, Neon is connected |
| 3 | Ask FitBot "what packages do you have?" | The database path works — this never calls an LLM |
| 4 | Ask FitBot how to improve squat depth | Gemini or Groq is reachable from Render; reply streams over SSE |
| 5 | Sign in as your admin | Auth, Argon2 verification and JWT signing all work |
| 6 | Refresh the page while on `/dashboard` | `_redirects` reached `dist/` |
| 7 | Upload a PDF (text or scan), then ask FitBot about it | Ingest (direct/OCR), embeddings, hybrid retrieve + pgvector |
| 8 | Admin → Insights → ask Copilot / analyst; refresh Advisor | Streamed prose + tables/recs on `done`; metric registry |
| 9 | Create a reception user (or promote one), open `/front-desk` | New role + route guard |
| 10 | Member → My gym pass → Front desk Scan → Confirm | QR pass, briefing and attendance write |

Camera check-in needs HTTPS (Pages already is). After the first deploy that adds reception,
startup runs `ALTER TYPE role ADD VALUE IF NOT EXISTS 'RECEPTION'` on Neon before you create
desk accounts.

If step 1 works but step 2 fails, it is almost always `FRONTEND_ORIGIN`.

---

# Part 4 — Operating it

## 4.1 Shipping a change

`git push`. Render rebuilds the backend, Cloudflare rebuilds the frontend, both automatically
(`autoDeploy: true`). Cloudflare also builds every pull request into a preview URL.

## 4.2 Changing the database schema

This needs a thought, because `initialize_database()` **only creates tables that are missing —
it never alters an existing one.**

| Change | What happens |
| --- | --- |
| New model | The table appears on the next deploy. Nothing to do. |
| New column on an existing table | **Silently does not reach the database.** The app then fails when it reads that column. |
| Changed column type | Same. Nothing happens. |
| New `Role.RECEPTION` on hosted Postgres | Startup runs `ALTER TYPE role ADD VALUE IF NOT EXISTS 'RECEPTION'`. Safe to redeploy. |

While the data is disposable, rebuild it:

```powershell
cd backend
$env:DATABASE_URL = "<neon connection string>"
..\.venv\Scripts\python.exe -m scripts.reset_db --yes --admin-email you@example.com --admin-password "..." --public-demo
```

That drops the schema, recreates it from the current models, reseeds the packages and restores
your admin. Uploaded PDFs are cleared too, so re-upload them.

**Once real members exist, stop doing this and add Alembic.** It is the first thing this project
would need in order to be taken seriously in production.

## 4.3 Rolling back

One click each: Render → **Deploys** → pick an earlier one → **Redeploy**. Cloudflare →
**Deployments** → pick one → **Rollback**.

Neither rolls back the database. If a deploy changed the schema, roll the code back and fix the
data separately.

## 4.4 Logs and what to look for

Render → your service → **Logs** is the live stream.

| Log line | Meaning |
| --- | --- |
| `Master GYM starting, model=...` | Startup succeeded |
| `gemini usage: prompt=... output=... total=...` | Token counts per call — this is how the prompt budget was measured |
| `gemini is out of quota, skipping it for 900s` | The cooldown kicked in; Groq is answering now |
| `every configured provider refused the request` | Both are down or both are out |
| `Retrieval failed, answering without documents` | pgvector or embeddings failed; FitBot degraded rather than erroring |

There is no error tracker wired up. Sentry's free tier would be the obvious addition.

## 4.5 The cold start

The free Render instance spins down after 15 minutes without a request and takes roughly 50
seconds to wake. Nothing is lost, it is just slow. The UI raises the "waking the demo server"
banner after 3 seconds so the wait reads as expected rather than broken.

**If you are demoing to somebody, load the site a minute beforehand.** This is the single most
useful operational fact in this document.

You could ping `/api/health` on a schedule to keep it warm, but free instance hours are capped
at 750 a month and a constant ping burns them for no benefit while nobody is visiting.

## 4.6 Rotating a key

Do this if a key is ever exposed, and once a year regardless.

| Key | How |
| --- | --- |
| `GEMINI_API_KEY` | Delete it in AI Studio, create a new one, update Render → Environment |
| `GROQ_API_KEY` | Same, in the Groq console |
| `JWT_SECRET` | Render → Environment → regenerate. **This signs every user out**, which is exactly what you want if it leaked |
| `DATABASE_URL` | Neon → reset the role password, update Render |

Render restarts on any environment change, so the new value is live within a minute.

## 4.7 Backups

The free Neon plan gives a 6-hour instant-restore window, which covers "I ran the wrong script
five minutes ago" and nothing longer. There are no scheduled snapshots on the free plan.

For a portfolio project that is fine, because the data is demo data and `scripts/seed.py`
recreates it. If you ever care about it:

```powershell
pg_dump "<neon connection string>" -Fc -f mastergym-backup.dump
```

## 4.8 Adding a custom domain

Not required, but it looks better on a resume than `pages.dev`.

1. Cloudflare Pages → your project → **Custom domains** → add `mastergym.yourdomain.com`.
   If the domain is already on Cloudflare, DNS is automatic; otherwise add the CNAME it shows
   you.
2. **Then update `FRONTEND_ORIGIN` on Render** to the new origin, or the API will start
   rejecting the site. This is the step people forget.
3. The Hobby plan includes two custom domains.

The API can stay on `onrender.com` — nobody reads that URL.

---

# Part 5 — Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| "Blocked by CORS policy" in the console | `FRONTEND_ORIGIN` does not match the site origin | Include the scheme, no trailing slash, restart |
| Site loads, every request 404s | `VITE_API_URL` missing or wrong at build time | Fix it in Cloudflare **and trigger a rebuild** — editing the variable alone does nothing |
| 404 when refreshing on `/dashboard` | `_redirects` did not reach `dist/` | Confirm output directory `dist` and root directory `frontend` |
| First request takes about a minute | Free instance waking | Expected. Not a bug |
| Render build fails on `pip install` | Python version or a dependency needing a compiler | Check `PYTHON_VERSION` is `3.14.3` |
| Health check passes, `/api/plans` returns 500 | Cannot reach Neon | Check `DATABASE_URL` is the **pooled** string with `?sslmode=require` |
| "FitBot is not configured yet" | Neither API key is set | Add `GEMINI_API_KEY` or `GROQ_API_KEY` |
| "I could not reach the coaching model" | Both providers refused | Logs show 401 for a bad key, 429 for exhausted quota. Remember the 15-minute cooldown |
| FitBot answers but never cites a document | No PDFs ingested for that discipline, or embeddings failed | Upload a PDF; check logs for `Retrieval failed` |
| FitBot still shows one complete reply | Frontend reached an older backend, or an old frontend build is cached | Deploy both current builds; the client intentionally falls back to `/fitbot/chat` when SSE cannot start |
| Insights answers arrive all at once / no stream | Same version skew on `/admin/.../stream` routes | Redeploy API + Pages; UI falls back to JSON ask/report endpoints |
| Database error after a quiet period | Neon was asleep, pooled connection stale | `pool_pre_ping` handles it; confirm you used the pooled string |
| 429 from your own API | The rate limiter | Expected. 20 chat messages per 5 minutes per caller |
| Cloudflare build fails, "no package.json" | Root directory not set | Set root directory to `frontend` |
| Demo login gets 403 on every save | Working as designed | Those three accounts are read-only |

---

# Part 6 — Security checklist

Before you share the link:

- [ ] `backend/.env` is gitignored and was **never** committed (Step 0 verifies this)
- [ ] `JWT_SECRET` in production is Render's generated value, not the dev placeholder
- [ ] `FRONTEND_ORIGIN` lists only origins you control — not `*`
- [ ] `RATE_LIMIT_ENABLED` is true
- [ ] The public demo accounts exist and are in `DEMO_ACCOUNT_EMAILS`, so they cannot write
- [ ] Your real admin password is strong and is not one of the demo passwords
- [ ] Your Gemini API key is restricted to the Gemini API (see Part 7)
- [ ] `pip install .` installs without the `[dev]` extras in production, so pytest is not shipped
- [ ] The catch-all handler in `main.py` means stack traces never reach the browser

Already handled by the code, worth knowing: passwords are Argon2 hashed, the `role` claim in the
JWT is never trusted (the server re-reads `user.role` from the database on every request), an
admin cannot demote or deactivate themselves, chat transcripts are readable only by their owner,
and document retrieval is filtered by the caller's package inside the SQL query.

---

# Part 7 — Money: can this ever charge you?

**Short answer: no, provided you never add a payment method to Render, Cloudflare or Neon, and
you never link billing to the Google Cloud project behind your Gemini key.**

The detail matters, so here it is properly.

## 7.1 The three hosts cannot bill you without a card

None of the three requires a payment method, and all three **suspend the service rather than
charging you** when you have no card on file. Render states this explicitly in its own FAQ:

> "If you haven't added a payment method and you would incur charges, Render instead disables
> your services for the duration of the current billing period."

| Host | Free allowance | What happens at the limit |
| --- | --- | --- |
| **Render** (Hobby) | 750 instance hours/month, 500 build minutes, 5 GB outbound bandwidth | Service disabled until next billing period. No card, no charge |
| **Cloudflare Pages** | Unlimited requests and bandwidth, 500 builds/month | Builds queue or stop. No overage billing |
| **Neon** (Free) | 0.5 GB storage, 100 compute-hours, 5 GB egress per project per month | Compute suspended until next month. **Your data is not deleted** |

Two notes specific to your setup. Render's Hobby plan changed on 23 April 2026: included
outbound bandwidth dropped from 100 GB to 5 GB, with $0.15/GB beyond that. For a site with
recruiter-level traffic, 5 GB is a lot — the heavy assets are on Cloudflare, and Render only
serves JSON. And Neon's free plan is permanent, not a trial, so it does not expire after 30
days the way Render's own managed Postgres does. That is a good reason you are on Neon.

Worst realistic case if your link somehow goes viral: **the site goes offline until next month.
You do not get a bill.**

## 7.2 The one thing that could actually cost money

**The Gemini API key — and only if its project has billing linked.**

Google's model works like this:

| Tier | How you get there | Monthly cap |
| --- | --- | --- |
| **Free** | Default for a new AI Studio key | Not applicable — you just get rate limited (429) |
| Tier 1 | You link an active Cloud Billing account | **$250** |
| Tier 2 | $100 paid, 3+ days later | $2,000 |

A Free Tier key **cannot** generate charges. When you hit the limit you get
`429 RESOURCE_EXHAUSTED`, which this app already handles: it puts Gemini on a 15-minute cooldown
and falls through to Groq. The member never sees a failure.

The risk is if that project is linked to billing — perhaps because you once used Google Cloud
for something else, or clicked "Set up billing" in AI Studio. Then the same key bills per token
up to $250 a month.

**Go and check now.** Open https://aistudio.google.com/apikey and look at the **Billing Tier**
column for your key's project. If it says **Free**, you are safe and nothing further is needed.
If it says Tier 1 or shows a linked billing account, either unlink billing from that project or
create a fresh key in a project with no billing and update Render.

Groq's free tier has no card and no paid overflow, so it carries no risk at all.

## 7.3 The bigger risk is a stolen key, not a traffic spike

If a key leaks and the project has billing, someone else spends your money. This is the actual
way people get surprise bills from side projects.

I checked your repository: **`.env` has never been committed in any branch at any point in
history, and `.gitignore` correctly excludes `.env` and `*.db`.** Only `backend/.env.example`
and `frontend/.env.example` are tracked, which is right. Your keys live only in your local
`.env` and in Render's environment settings, neither of which is public.

Two more protections, one of which is now mandatory:

- **Restrict the key.** Since 19 June 2026 the Gemini API rejects unrestricted API keys. Keys
  created in AI Studio are restricted to the Gemini API by default. If yours came from the Cloud
  console, restrict it: Google Cloud → Credentials → your key → API restrictions →
  `generativelanguage.googleapis.com`.
- **Your app already limits abuse.** `rate_limit("chat", 20, 300)` caps any single caller at 20
  chat messages per 5 minutes, and the prompt budget keeps each call around 740 tokens. Someone
  cannot loop your chat endpoint to drain a quota quickly.

## 7.4 So should you keep it deployed for your resume?

**Yes. Keep it up.** A live link that a recruiter can click is one of the highest-value things
on a resume — it converts "claims to have built a full-stack AI app" into thirty seconds of
proof. Taking it down to avoid a charge that cannot happen would be trading a real benefit for
an imaginary risk.

Do these four things and you are done:

1. Confirm your Gemini key's project shows **Free** billing tier. This is the only real risk.
2. Add no payment method to Render, Cloudflare or Neon. Without one they suspend, never bill.
3. Leave `RATE_LIMIT_ENABLED` true.
4. Keep the demo accounts read-only, as they already are.

Then set an expectation on the resume itself. Because the free instance sleeps, write the link
as:

> **Live demo** (free tier — first load takes ~50s to wake): https://master-gym.pages.dev
> Demo logins on the sign-in page.

That one parenthesis turns a slow first load from "this is broken" into "this person understands
what they deployed on". Recruiters and engineers both read that well.

## 7.5 If you still want zero AI spend while staying live

There is a middle option, and the app was built for it: **remove `GEMINI_API_KEY` and
`GROQ_API_KEY` from Render's environment.**

Everything degrades gracefully instead of breaking:

| Still works | Stops working |
| --- | --- |
| The whole site, member / trainer / admin / front-desk | FitBot's model-generated coaching answers |
| FitBot's price and timetable answers (read from Postgres) | Document retrieval (embeddings need Gemini) |
| The safety gate, login and upgrade prompts | The analyst's written narration |
| The advisor's recommendations — findings are computed, not generated | The advisor's written briefing |
| Every dashboard, booking, programme and admin function | |

FitBot will say it needs a key configured rather than erroring. So you keep a working, clickable
site with genuinely zero external API usage. I would not do this — the assistant is the most
impressive part — but it is there if you want it, and it needs no code change, just deleting two
environment variables.

---

# Part 8 — Taking it down cleanly

If you ever want to stop, in this order:

1. **Render** → Settings → Suspend (reversible) or Delete. Stops all API traffic and any LLM
   calls.
2. **Cloudflare Pages** → Settings → Delete project. Or just leave it: a static site with no
   working API costs nothing and does nobody any harm.
3. **Neon** → delete the project. Do this last, and export first if you want the data.
4. **Revoke the API keys** in AI Studio and the Groq console. Do this even if you deleted
   everything else — a live key is a live key.

Suspending Render alone is enough to stop all activity and all conceivable spend, and it is one
click to bring back. That is what I would do if you needed a pause rather than an ending.

---

# Part 9 — MCP (local only, not part of the hosted deploy)

The backend ships two Model Context Protocol servers (`app/mcp_server.py`, `app/mcp_admin.py`).
They run on **your laptop** via stdio for Cursor / Claude Desktop. They are **not** deployed on
Render. Wire them only on a machine you control; use the same `DATABASE_URL` and `JWT_SECRET`
as the API. Admin Copilot MCP requires `admin_login` then a `session_token` — never put the
password on every question. Details: [backend/BACKEND.md](backend/BACKEND.md).

---

## Related documents

- [README.md](README.md) — what the project is and how to run it locally
- [DEPLOYMENT.md](DEPLOYMENT.md) — the original record of how this project went live
- [backend/BACKEND.md](backend/BACKEND.md) — the server in detail
- [frontend/FRONTEND.md](frontend/FRONTEND.md) — the browser app in detail
- [EXPLANATION.md](EXPLANATION.md) — the decisions and how to present them
