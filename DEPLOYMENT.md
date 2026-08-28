# Deploying Master GYM

This is the full record of how Master GYM goes live: what had to change in the code, why each
change was needed, and the exact steps to follow in the Render and Cloudflare dashboards.

Everything here stays on free tiers.

## Live addresses

| Piece | Address |
| --- | --- |
| Repository | https://github.com/ummmarrr/GYM- |
| API | https://master-gym-api.onrender.com |
| Health check | https://master-gym-api.onrender.com/api/health |
| Site | https://master-gym.pages.dev |

The Render service is named `master-gym-api`, runs in Singapore on the free plan, and is
managed by the `master-gym` blueprint, so editing `render.yaml` and pushing updates it.

---

## 1. The shape of the deployment

Three services, each doing the one thing it is good at:

| Piece | Host | Why |
| --- | --- | --- |
| FastAPI backend | Render (free web service) | Runs Python, gives a public HTTPS URL |
| React frontend | Cloudflare Pages | Static files on a CDN, unlimited free bandwidth |
| Postgres + pgvector | Neon (free tier) | Persistent storage that survives redeploys |

The important idea is that **Render's filesystem is ephemeral**. Anything written to disk is
gone on the next deploy and every time the free instance wakes from sleep. That is why the
project moved from SQLite to Neon and from ChromaDB to pgvector: after that migration nothing
the app cares about lives on disk, so a disposable filesystem stops being a problem.

---

## 2. Code changes made for deployment

Four changes, all small, all already done and verified.

### 2.1 The frontend can now be told where the API is

In development, Vite proxies `/api` to `127.0.0.1:8000`, so the browser only ever sees one
origin. In production the site and the API are on different domains, so relative URLs break.

`frontend/src/lib/api.ts` now reads a base URL from the environment and falls back to empty,
which preserves the local proxy behaviour exactly:

```ts
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
// ...
const response = await fetch(`${API_BASE}/api${path}`, { ... });
```

There is exactly one `fetch` in the whole frontend, so this single line covers every call.

`frontend/src/vite-env.d.ts` was added so TypeScript knows about `import.meta.env.VITE_API_URL`,
and `frontend/.env.example` documents the variable.

### 2.2 CORS accepts more than one origin

The backend previously allowed a single origin. Once deployed you need at least the live site,
and usually localhost too so you can keep developing against production data if you want.

`FRONTEND_ORIGIN` is now read as a comma-separated list (`backend/app/core/config.py`):

```python
@property
def allowed_origins(self) -> list[str]:
    return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]
```

### 2.3 Client-side routing survives a refresh

React Router owns paths like `/login` and `/dashboard`, but those files do not exist on disk.
Without a rule, refreshing on `/login` returns a 404 from the CDN. `frontend/public/_redirects`
serves the app shell for any unmatched path:

```
/*  /index.html  200
```

Vite copies `public/` into `dist/`, so this ships automatically with every build.

### 2.4 Per-caller rate limits

FitBot answers signed-out visitors, and every message costs an embedding call and an LLM call.
On a public URL, one loop could drain both providers' free quotas and fill the database with
conversation rows, so `backend/app/core/rate_limit.py` caps the endpoints anyone can reach:
20 chat messages and 10 login attempts per five minutes, and 5 signups an hour, each counted
per caller. Over the limit returns 429 with a `Retry-After` header.

The counter is held in the process, which suits a single free Render instance. Running more
than one instance would need a shared store such as Redis, because each process would
otherwise grant the full allowance on its own.

Behind Render's proxy the socket address belongs to the proxy, so the caller is taken from the
first entry of `X-Forwarded-For`.

### 2.5 A Render blueprint

`render.yaml` at the repository root describes the backend service, so Render configures itself
instead of you filling in a form. It pins Python 3.14.3, sets `rootDir` to `backend`, runs the
health check against `/api/health`, generates `JWT_SECRET` automatically, and marks the secrets
as `sync: false` so they are never committed.

---

## 3. Before you start

You need accounts on **GitHub**, **Render** and **Cloudflare** (all free), plus the Neon project
you already created. Have these values ready:

| Value | Where it comes from |
| --- | --- |
| `DATABASE_URL` | Neon dashboard, Connection string (the pooled one) |
| `GEMINI_API_KEY` | Google AI Studio |
| `GROQ_API_KEY` | console.groq.com |

They are all already in `backend/.env`. Copy them from there.

> **Never commit `backend/.env`.** `.gitignore` excludes it. If the repository is public, treat
> any key that reaches it as burnt and rotate it.

---

## 4. Step one: get the code onto GitHub

Both hosts deploy from a Git repository, so the project needs one. From the project root:

```powershell
git init
git add -A
git commit -m "Master GYM: gym platform with the FitBot assistant"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

Before pushing, confirm no secrets are staged:

```powershell
git status --short | Select-String ".env"
```

You should see `backend/.env.example` and `frontend/.env.example` only. If `backend/.env`
appears, stop and fix `.gitignore` first.

A private repository is recommended.

---

## 5. Step two: the backend on Render

1. Sign in to [Render](https://dashboard.render.com) with GitHub.
2. Click **New > Blueprint** and select the repository. Render reads `render.yaml` and proposes
   a service called `master-gym-api`.
3. It will prompt for the four values marked `sync: false`. Paste them:

   - `DATABASE_URL` — the Neon connection string, exactly as Neon gives it. The app rewrites
     `postgresql://` to `postgresql+psycopg://` itself, so no editing needed.
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
   - `FRONTEND_ORIGIN` — you do not have the Pages URL yet. Put `http://localhost:5173` for now
     and correct it in step four.

4. Click **Apply**. The first build takes roughly three to five minutes, mostly compiling
   dependencies.
5. When it goes live, open `https://<your-service>.onrender.com/api/health`. You want:

   ```json
   {"status": "ok", "app": "Master GYM", "bot": "FitBot"}
   ```

Note the service URL. You need it in the next step.

**What happens on first boot:** the app's lifespan hook runs `initialize_database()`, which
enables the `vector` extension, creates any missing tables and seeds the three packages. Since
your Neon database is already set up, it will find everything present and change nothing.

---

## 6. Step three: the frontend on Cloudflare Pages

1. Sign in to [Cloudflare](https://dash.cloudflare.com) and go to **Workers & Pages > Create >
   Pages > Connect to Git**.
2. Pick the same repository, then set:

   | Setting | Value |
   | --- | --- |
   | Framework preset | Vite |
   | Build command | `npm run build` |
   | Build output directory | `dist` |
   | Root directory | `frontend` |

3. Under **Environment variables**, add `VITE_API_URL` set to your Render URL with no trailing
   slash, for example `https://master-gym-api.onrender.com`.

   This is baked into the JavaScript at build time, not read at runtime. Changing it later means
   triggering a fresh build.

4. Deploy. You get a URL like `https://master-gym.pages.dev`.

---

## 7. Step four: introduce them to each other

The browser will refuse to call the API until the backend names the site as an allowed origin.

In Render, open your service, go to **Environment**, and set `FRONTEND_ORIGIN` to your Pages URL:

```
https://master-gym.pages.dev
```

Keep localhost too if you want to develop against production:

```
https://master-gym.pages.dev,http://localhost:5173
```

Save. Render restarts the service automatically.

---

## 8. Step five: verify the live site

Work through these in order. Each one exercises a different layer.

1. **Open the site.** The landing page and packages load. That proves Pages is serving the build
   and the API call for plans succeeded, which means CORS is right.
2. **Ask FitBot about prices.** The answer should be instant and list all three packages. This
   path never touches the LLM — it reads Neon directly — so it proves the database connection.
3. **Ask FitBot a coaching question**, such as how to improve squat depth. A real answer proves
   Gemini or Groq is reachable from Render.
4. **Log in as admin** with your existing credentials, since the deployed app shares your Neon
   database and your account is already there.
5. **Refresh the page while on `/dashboard`.** It should reload normally, proving `_redirects`
   is working.
6. **Upload a PDF** from the admin knowledge page and ask FitBot about its contents.

If step 1 fails but the API health check passes, it is almost always `FRONTEND_ORIGIN`.

---

## 9. Things worth knowing about the free tiers

**Render sleeps.** After 15 minutes without a request the free instance spins down. The next
visitor waits roughly 50 seconds while it wakes. Nothing is lost, it is just slow. Any request
still unanswered after three seconds raises a "waking the demo server" notice in the browser so
the wait reads as expected rather than broken (`ColdStartBanner`, fed by `onColdStart` in
`lib/api.ts`). If you are demoing the site to someone, load it a minute beforehand. Free
instance hours are capped at 750 a month, which one service cannot exceed.

**Neon gives you 0.5 GB.** Ample here. Rows are tiny; the only thing that grows meaningfully is
`knowledge_chunks`, where each PDF page costs a few kilobytes of text plus a 768-dimension
vector at about 3 KB. Hundreds of PDFs would still fit. Neon also suspends an idle database,
which is why `db.py` sets `pool_pre_ping` — a connection that died during the nap is detected
and replaced instead of throwing.

**Cloudflare Pages is effectively unlimited** for a site this size: unlimited bandwidth, 500
builds a month.

**One database serves both.** Your laptop and the deployed site currently share a single Neon
database, so local experiments change live data. That is fine now and worth revisiting the
moment real members exist — Neon branches give you a separate copy for development.

---

## 10. Day-to-day after deployment

**Shipping a change** is just `git push`. Render rebuilds the backend, Cloudflare rebuilds the
frontend, both automatically.

**Changing the database schema** needs a thought, because `initialize_database` only creates
tables that are missing — it never alters an existing one. Adding a new model is free: push and
the table appears. Adding a column to an existing table does not reach the database. While the
data is disposable, rebuild it:

```powershell
cd backend
..\.venv\Scripts\python.exe -m scripts.reset_db --yes --admin-email you@example.com --admin-password "..." --demo
```

That drops the schema, recreates it from the current models, reseeds the packages and puts your
admin back. Uploaded PDFs are cleared too, so re-upload them. Once you have real members, switch
to Alembic migrations instead.

**Rolling back** is one click in Render (Deploys > pick an earlier one > Redeploy) and one click
in Cloudflare (Deployments > pick > Rollback).

**MCP servers** (`python -m app.mcp_server` / `python -m app.mcp_admin`) are for local AI tools
on your own PC. They are not part of the Render service. See BACKEND.md for Cursor config.

**The visitor logins** on the sign-in page are `member-demo@`, `trainer-demo@` and
`admin-demo@example.com`. Recreate them at any time with:

```powershell
cd backend
..\.venv\Scripts\python.exe -m scripts.seed --public-demo
```

Because their passwords are public, `get_current_user` refuses every write from those three
addresses — the list is `demo_account_emails` in `app/core/config.py`, overridable with the
`DEMO_ACCOUNT_EMAILS` environment variable. Asking the data agent and booking a class stay
open, since neither survives the visit in a way another visitor would notice.

---

## 11. Troubleshooting

**"Blocked by CORS policy" in the browser console.** `FRONTEND_ORIGIN` on Render does not match
the site's origin. It must include the scheme and no trailing slash.

**The site loads but every request 404s.** `VITE_API_URL` was missing or wrong at build time.
Fix it in Cloudflare and trigger a new deployment; editing the variable alone does nothing
because the value is compiled into the bundle.

**A 404 when refreshing on a route.** `_redirects` did not reach `dist/`. Confirm the build
output directory is `dist` and the root directory is `frontend`.

**First request takes about a minute.** That is the free instance waking up. Expected.

**FitBot apologises that it cannot reach the coaching model.** Both providers refused. Check the
Render logs: an invalid key shows as a 401, an exhausted quota as a 429. Remember the app skips
a provider for 15 minutes after it reports its quota is gone.

**A database error right after a quiet period.** Neon was asleep and a pooled connection was
stale. `pool_pre_ping` handles this; if it persists, confirm `DATABASE_URL` is the pooled
connection string from Neon.
