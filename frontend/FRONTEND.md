# Frontend Guide

Everything about the browser side of Master GYM: the files, the routes, how login state is
kept, how every page works, and how the FitBot chat widget is built.

Written in plain English. Read top to bottom if the codebase is new to you.

---

## 1. What the frontend is

A single-page React app. No server-side rendering, no framework on top of React. It is served
as static files from a CDN and talks to the FastAPI backend over JSON.

It has to serve four different kinds of visitor from the same bundle:

1. A stranger reading the marketing page.
2. A member checking their plan, programmes and classes.
3. A trainer writing programmes and managing the timetable.
4. A receptionist running the permanent QR check-in tablet.
5. An admin managing people, PDFs and the Insights agents (Copilot, analyst, advisor).

---

## 2. Tech used, and why

| Thing | Choice | Why this one |
| --- | --- | --- |
| UI library | React 18.3 | The default choice, and the app is mostly forms and lists |
| Build tool | Vite 6 | Instant dev server, and its proxy removes all CORS setup locally |
| Language | TypeScript 5.7, strict | The API types are written once and every page gets checked against them |
| Routing | React Router 6.28 | Nested routes let one guard protect a whole group of pages |
| Styling | Tailwind CSS v4 | No separate config file, and no UI library to fight |
| Icons | lucide-react | Tree-shakeable SVG icons, one consistent set |
| Door scanning | `@zxing/browser` | Decodes the member QR locally; camera frames never leave the tablet |
| Pass display | `qrcode.react` | Renders the signed pass as SVG on the member dashboard |
| State | React context + hooks | The only shared state is "who is signed in". A store would be overkill |
| Browser tests | Playwright | 46 tests driving real Chromium |
| Linting | `tsc --noEmit` | Type errors are the errors that matter here |

Node 20 or newer. No ESLint or Prettier config — `npm run lint` is a type check.

Six runtime dependencies in total. The QR scanner is lazy-loaded only on `/front-desk`, so its
larger bundle does not slow the public site.

---

## 3. Folder map

```
frontend/
├── index.html                Page shell. <html class="dark">, inline SVG favicon
├── package.json              Scripts and dependencies
├── vite.config.ts            React + Tailwind plugins, /api dev proxy
├── tsconfig.json             Strict TypeScript, type-check only
├── playwright.config.ts      Chromium, one worker, 120s timeout
├── .env.example              Documents VITE_API_URL
├── public/
│   └── _redirects            Cloudflare SPA fallback
├── src/
│   ├── main.tsx              Entry: StrictMode → BrowserRouter → AuthProvider
│   ├── App.tsx               The route table
│   ├── index.css             Tailwind import, theme tokens, component classes
│   ├── vite-env.d.ts         Types for import.meta.env
│   ├── context/
│   │   └── AuthContext.tsx   Sign in, sign up, sign out, session hydration
│   ├── lib/
│   │   ├── api.ts            The only fetch in the app, plus every API type
│   │   └── format.ts         Money, dates, quotas, initials
│   ├── components/
│   │   ├── Layout.tsx        Header, footer, mobile menu, mounts the widget
│   │   ├── ProtectedRoute.tsx Role guard
│   │   ├── FitBotWidget.tsx  The chat widget
│   │   ├── ColdStartBanner.tsx "Waking the demo server" notice
│   │   └── ui.tsx            Button, Badge, Field, Alert, Spinner, Stat, EmptyState
│   └── pages/
│       ├── Landing.tsx       Marketing home
│       ├── Packages.tsx      Plans and activation
│       ├── Login.tsx         Sign in, plus demo shortcuts
│       ├── Join.tsx          Sign up
│       ├── MemberDashboard.tsx
│       ├── TrainerDashboard.tsx
│       ├── FrontDesk.tsx       QR kiosk for reception/admin
│       ├── AdminDashboard.tsx
│       └── AdminInsights.tsx
└── e2e/
    ├── helpers.ts            Credentials, sign in/out, error watcher
    ├── public.spec.ts        10 tests
    ├── fitbot.spec.ts        8 tests
    ├── member.spec.ts        7 tests
    ├── staff.spec.ts         13 tests
    └── insights.spec.ts      7 tests
```

The layering rule: **`pages/` fetch and arrange, `components/` render, `lib/` talks to the
network, `context/` holds shared state.** A page never calls `fetch` itself.

---

## 4. How the app boots

`src/main.tsx` nests four things, and the order matters:

```
StrictMode
  └── BrowserRouter        so routing hooks work anywhere
        └── AuthProvider   so any component can read the current user
              └── App      the route table
```

`AuthProvider` sits inside the router because it uses navigation, and outside `App` because
`ProtectedRoute` needs the user before deciding what to render.

On first paint `AuthProvider` starts with `loading: true`. Everything that depends on identity
waits for that flag, which is what stops a signed-in member from seeing a flash of the login
page on refresh.

---

## 5. Routes and the guard

All routes are children of `<Layout />`, so the header, footer and chat widget exist on every
page including the 404.

| Path | Page | Guard | Who gets in |
| --- | --- | --- | --- |
| `/` | `Landing` | none | everyone |
| `/packages` | `Packages` | none | everyone |
| `/login` | `Login` | none | everyone |
| `/join` | `Join` | none | everyone |
| `/dashboard` | `MemberDashboard` | `ProtectedRoute` | member, trainer, admin |
| `/trainer` | `TrainerDashboard` | `ProtectedRoute` | trainer, admin |
| `/front-desk` | `FrontDesk` | `ProtectedRoute` | reception, admin |
| `/admin` | `AdminDashboard` | `ProtectedRoute` | admin |
| `/admin/insights` | `AdminInsights` | `ProtectedRoute` | admin |
| `*` | `NotFound` | none | everyone |

### `ProtectedRoute`

```tsx
export default function ProtectedRoute({ allow }: { allow: Role[] }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner label="Checking your session" />;

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (!allow.includes(user.role)) {
    return <Navigate to={homeFor(user.role)} replace />;
  }

  return <Outlet />;
}
```

Three behaviours, in order:

1. **Still checking** — show a spinner. Never redirect while `loading` is true.
2. **Not signed in** — go to `/login`, remembering where they wanted to go in
   `state.from`. The login page reads it and sends them there afterwards, so a bookmarked
   `/admin` link still lands correctly after signing in.
3. **Wrong role** — send them to their own home via `homeFor(role)`: admin → `/admin`,
   trainer → `/trainer`, member → `/dashboard`. A redirect rather than an error page, because
   a member reaching `/admin` is a wrong turn, not a failure.

`replace` is used on both redirects so the back button does not bounce the user in a loop.

**This guard is only about user experience.** It hides links and prevents pointless page
loads. Every real permission check happens on the server, and the server does not trust the
browser. If you deleted `ProtectedRoute` entirely, the app would look broken but nothing would
leak — the API would still return 401 and 403.

---

## 6. Login state (`src/context/AuthContext.tsx`)

The context exposes exactly what pages need:

```ts
interface AuthValue {
  user: User | null;
  entitlements: Entitlements | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  signUp: (payload: { email: string; full_name: string; password: string; phone?: string }) => Promise<User>;
  signOut: () => void;
  refresh: () => Promise<void>;
}
```

`useAuth()` throws if used outside the provider, which turns a confusing null crash into a
clear message.

**Entitlements live next to the user on purpose.** Almost every screen needs both — the
member dashboard shows days remaining, the packages page marks your current plan, the chat
widget decides whether to offer an upgrade. Fetching them together means one source of truth
and no page-by-page duplication.

### Where the token is kept

`localStorage`, under `mastergym.token`:

```ts
const TOKEN_KEY = "mastergym.token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};
```

`localStorage` survives a refresh and a closed tab, which is what you want for an 8-hour
token. The honest trade-off: `localStorage` is readable by any script on the page, so it is
weaker against XSS than an httpOnly cookie. The cookie approach would need CSRF protection
and shared-domain handling across Cloudflare Pages and Render, which is real complexity. For
this app the trade was accepted knowingly, not by accident.

### The flows

**Sign in** → `api.login()` → store the token → `api.me()` → `api.entitlements()` → return
the user so the caller can redirect by role.

**Sign up** → `api.register()` → the same steps after the token. Signing up leaves you signed
in; there is no second login step.

**Sign out** → clear the token, null the user and entitlements. Nothing to call on the server,
because tokens are stateless.

**Refresh** → re-run the load. Called after anything that changes entitlements, like buying a
package or booking a class.

### Hydration on page load

```ts
const load = useCallback(async () => {
  if (!tokenStore.get()) {
    setUser(null);
    setEntitlements(null);
    setLoading(false);
    return;
  }
  try {
    const profile = await api.me();
    setUser(profile);
    setEntitlements(await api.entitlements());
  } catch {
    tokenStore.clear();
    setUser(null);
    setEntitlements(null);
  } finally {
    setLoading(false);
  }
}, []);
```

No token means no request at all — a visitor costs the API nothing. An expired or invalid
token is discovered by `api.me()` failing, and the bad token is thrown away rather than left
to fail again on the next page.

There is **no refresh token and no expiry timer.** The token simply stops working and the
member signs in again. `request()` also clears the token on any 401, so a session that dies
mid-visit cleans itself up.

---

## 7. The API client (`src/lib/api.ts`)

### One fetch, one place

There is exactly one `fetch` call in the whole frontend:

```ts
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

response = await fetch(`${API_BASE}/api${path}`, {
  ...init,
  headers: {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...init.headers,
  },
});
```

That single line is why deployment needed only a one-line change. In development
`VITE_API_URL` is unset, so `API_BASE` is empty, requests go to `/api/...`, and Vite's proxy
forwards them to `127.0.0.1:8000`. Same origin, no CORS. In production `VITE_API_URL` is set
to the Render URL and the same code produces absolute URLs.

Note that `VITE_API_URL` is baked in at **build** time, not read at runtime. Changing it means
triggering a new build.

`Content-Type` is skipped for `FormData` so the browser can set the multipart boundary itself.
That is required for the PDF upload to work.

### Errors

```ts
class ApiError extends Error {
  status: number;
}
```

- `readDetail()` unpacks FastAPI's `detail` field, which is a string for `HTTPException` and
  an array for validation failures. Both become one readable sentence.
- A 401 clears the stored token before throwing.
- 204 responses return `undefined` instead of trying to parse empty JSON.

Because backend errors are written for members, pages can show `error.message` directly. No
mapping table of codes to copy.

### Cold-start detection

The free Render instance sleeps after 15 minutes and takes about 50 seconds to wake:

```ts
const COLD_START_MS = 3000;
```

If a request has not been answered after three seconds, `onColdStart(true)` fires and
`ColdStartBanner` appears with "Waking the demo server...". The wait is unavoidable on a free
plan; the banner makes it read as expected rather than broken.

### The typed surface

Every backend response has a matching interface: `User`, `Plan`, `Entitlements`, `GymClass`,
`Person`, `Programme`, `Profile`, `Overview`, `KnowledgeDoc` (includes optional `ingest_mode`),
`MetricTable`, `AnalystAnswer`, `Recommendation`, `AdvisorReport`, `ChatReply`, plus the unions
`Role`, `Priority` and `ChatAction`.

About thirty functions grouped on one `api` object, named after intent rather than HTTP:

| Group | Functions |
| --- | --- |
| Auth | `login`, `register`, `me` |
| Packages | `plans`, `entitlements`, `buyPlan` |
| Classes | `classes`, `bookClass`, `cancelBooking`, `createClass`, `deleteClass` |
| Member | `profile`, `saveProfile`, `myProgrammes` |
| Admin people | `people`, `createPerson`, `updatePerson`, `changeRole`, `assignTrainer`, `overview` |
| Staff | `myMembers`, `memberProgrammes`, `createProgramme` |
| Knowledge | `documents`, `uploadDocument`, `deleteDocument` |
| AI | `chat`, `metrics`, `askAnalyst`, `advisorReport`, `askCopilot` |

These types are written by hand rather than generated from the OpenAPI schema. For an app this
size that is less machinery, and a mismatch shows up immediately as a type error in the page
that uses it.

### Formatting (`src/lib/format.ts`)

| Function | Does |
| --- | --- |
| `rupees(paise)` | Paise to `₹1,499` using `Intl.NumberFormat` |
| `parseApiDate(value)` | Appends `Z`, because the backend sends naive UTC |
| `longDate(value)` | `10 Aug 2026` |
| `classTime(value)` | Weekday, date and time |
| `quotaLabel(quota)` | `Unlimited`, `None`, or `8 / month` |
| `initials(name)` | Two letters for the avatar |

`parseApiDate` is small but load-bearing. The backend stores naive UTC datetimes, so
`new Date(value)` in the browser would read them as local time and every class would appear at
the wrong hour.

---

## 8. The pages

### `Landing.tsx` — `/`

Marketing only, no data fetching. Hero with a "Now with FitBot" badge and the headline "Train
with intent. Not guesswork.", then the three disciplines, then features, then a closing call to
action. Elements use `animate-rise`.

The buttons adapt to who is reading: a visitor sees "Start training" and "See packages", while
a signed-in user sees "Go to my dashboard" pointing at `homeFor(user.role)`.

### `Packages.tsx` — `/packages`

Fetches `api.plans()` and reads `entitlements` from context.

Three cards, with `tier === "performance"` marked as featured. `perks(plan)` turns the plan
flags into a readable list. The button has three states:

- signed out → "Join and choose", which navigates to `/join` carrying `state.planId`
- signed in → "Activate", which calls `api.buyPlan(plan.id)` then `refresh()`
- already yours → "Your current package", disabled

A `busyId` state tracks which card is loading, so only the clicked button shows a spinner. The
page states plainly that payment is simulated.

### `Login.tsx` — `/login`

Email and password, both required. After signing in it goes to `location.state.from` if the
guard put one there, otherwise `homeFor(user.role)`.

It also prints three demo logins with their passwords, which is exactly why the backend blocks
writes from those accounts. The page notes that admin accounts cannot be created from the
browser.

### `Join.tsx` — `/join`

Full name (min 2), email, optional phone, password (min 8). Validation is HTML attributes plus
whatever the server says, rather than a validation library — the fields are few and the server
is the real authority.

If the visitor arrived from a package card, `location.state.planId` is read and the plan is
activated right after signup, so choosing a package and joining is one flow instead of two.
A failure there is swallowed deliberately: the account exists, and the user can activate again
from the packages page.

### `MemberDashboard.tsx` — `/dashboard`

Loads `api.classes()`, `api.myProgrammes()` and `api.profile()`, and reads `user` and
`entitlements` from context.

Four sections:

1. **Membership** — plan name, expiry, disciplines, class quota, whether a personal programme
   is included. With 7 days or fewer left it shows an expiring badge. No package shows a call
   to action instead.
2. **My programmes** — the workout and diet plans a trainer wrote, with an empty state when
   there are none.
3. **Upcoming classes** — one button per class that books or cancels. `toggleBooking` then
   refreshes both the class list and entitlements, because a booking changes the quota shown
   above.
4. **My fitness profile** — goal, experience level, equipment access, injuries or limits. The
   success message mentions that FitBot reads this, which is the reason to fill it in.

A refusal from the server, such as booking a discipline your package excludes, is shown as-is.
The UI does not try to predict the rule; it asks and reports.

### `TrainerDashboard.tsx` — `/trainer`

Loads `api.myMembers()` and `api.classes()`, then `api.memberProgrammes(id)` when a member is
selected.

Stats row, then a two-column layout: the member roster on the left, the programme panel on the
right. Selecting a member loads their existing programmes and reveals the assign form (type,
title, details). Below that, the timetable with an add form (name, discipline,
`datetime-local`, capacity 1–200) and delete buttons.

The roster only contains members assigned to this trainer, because that is what
`GET /api/trainer/members` returns for a trainer. The filtering is on the server, not here.

One detail: `starts_at` is sent as `new Date(startsAt).toISOString().slice(0, 19)`, dropping
the timezone marker to match the naive UTC datetimes the backend stores.

### `FrontDesk.tsx` — `/front-desk`

A tablet-friendly check-in kiosk for reception and admin. ZXing reads a secure member QR
directly from the camera, then the API returns the member photo, package/expiry, upcoming
bookings, trainer, active repair notices and last check-in. The receptionist confirms the
human match before attendance is written. Manual member search is the fallback for a forgotten
card. FitBot and the marketing footer are hidden on this route.

### `AdminDashboard.tsx` — `/admin`

Loads `api.overview()`, `api.people()` and `api.documents()` in parallel, so the page paints
once rather than in three steps.

1. A card linking to `/admin/insights`.
2. Four stats: members, active packages, revenue, knowledge documents.
3. Create member or trainer — name, email, temporary password, role.
4. The accounts table, where the actions are inline controls rather than modals: a role
   dropdown, a trainer dropdown, and a clickable active badge that toggles the account.
5. The FitBot knowledge base — a PDF upload with a discipline dropdown, and the document list
   with chunk counts, ingest mode (`direct` vs `ocr`), and delete buttons. Scanned PDFs are
   OCR'd on the backend (needs Gemini); text PDFs extract tables and image summary/detail too.

Small but real bug fix worth keeping: the role dropdown captures its value into a variable
before the `await`, because a controlled `<select>` would otherwise snap back to the old value
while the request is in flight.

### `AdminInsights.tsx` — `/admin/insights`

Three tabs. Default is **Copilot**.

**Copilot tab** — one textbox for the multi-agent orchestrator. Empty state explains DataAgent /
AdvisorAgent / Both, with sample chips labeled accordingly. Each reply shows which agents ran,
plus any metric tables and recommendation cards they produced. Calls `api.askCopilot`.

**Analyst tab** — five suggested questions, then a chat-style list of turns with `MetricGrid`
for the tables the agent actually read. Input capped at 500 characters.

**Advisor tab** — briefing card with summary, refresh, and `RecommendationCard` grid. Fetched
on first open of the tab.

None of these are streamed. One POST, one full response.

---

## 9. Components

### `Layout.tsx`

The shell every page sits in: a sticky blurred header with the brand and nav, the
`ColdStartBanner`, `<main><Outlet /></main>`, a footer, and `FitBotWidget`. Below `md` the nav
collapses into a hamburger menu with an `open` state. The right side of the header shows an
avatar and sign-out when signed in, or sign-in and join links when not.

The widget is mounted here rather than per page, so the chat is available everywhere and its
state survives navigation.

### `ColdStartBanner.tsx`

Subscribes to `onColdStart` and renders a small fixed pill with a spinner while the API is
waking. Returns `null` the rest of the time.

### `FitBotWidget.tsx`

The most interesting component in the app.

**State:**

| State | Purpose |
| --- | --- |
| `open` | Collapsed button or expanded dialog |
| `bubbles` | The messages so far |
| `draft` | The input text |
| `conversationId` | Returned by the server on the first reply, sent back on every later one |
| `thinking` | Shows the typing dots and disables send |
| `authMode` | `"login"`, `"signup"` or `null` — whether to show the in-chat auth card |

Each bubble carries what it needs to render itself:

```ts
interface Bubble {
  id: number;
  from: "you" | "fitbot";
  text: string;
  sources?: string[];
  handoff?: boolean;
  action?: ChatAction;
}
```

**Sending** is one `api.chat(message, conversationId)` call. Not streamed, so the reply appears
all at once after the typing dots.

**Suggested prompts** appear while only the greeting exists: "What packages do you have?",
"Give me a beginner push day", "How do I improve my flexibility?". They exist because an empty
chat box is a hard thing to start with, and each one demonstrates a different path through the
backend — the first is answered from the database, the second and third from the model.

**The in-chat sign-in form** is the part worth explaining in an interview. When the backend
returns `action: "login"` or `action: "signup"`, the widget does not ask for credentials as
chat messages. It renders `SecureAuthCard`, a real form that calls `signIn` or `signUp` from
the auth context, exactly like the login page does.

Two reasons this matters. First, a password typed as a chat message would be saved into
`chat_messages` and sent to the model on later turns as history. Second, teaching users that a
chatbot may ask for passwords is teaching them to be phished. On success the widget clears
`authMode`, calls `refresh()` so entitlements update, and adds a "You're signed in" bubble so
the conversation continues where it left off.

**Sources** from `reply.sources` become strings like `protocol.pdf p.3`, deduplicated and shown
as a "From: ..." footer. Answers are checkable rather than just confident.

**Actions:** `login` and `signup` show the auth card; `upgrade` shows a "See upgrade options"
button that closes the widget and navigates to `/packages`.

**Handoff:** when `needs_human_handoff` is true the bubble gets an amber "Flagged for a human
trainer" note with a lifebuoy icon. That is the safety gate surfacing in the UI, so a member
asking about chest pain sees a clear route to a person.

Smaller touches: Escape closes the dialog, the input caps at 4000 characters to match the
backend's own limit, signed-in users get a dashboard link in the footer, and messages carry
`data-testid="fitbot-message"` for the Playwright tests.

### `ui.tsx`

Nine small primitives instead of a component library:

| Export | What it is |
| --- | --- |
| `Button` | Variants `primary`, `ghost`, `outline`, `danger`, plus a `busy` spinner state |
| `ButtonLink` | A router `Link` styled as a button |
| `Badge` | Pill with tones `neutral`, `volt`, `warn`, `danger` |
| `Field` | Label plus hint, and it clones its child to wire up `id` and `aria-describedby` |
| `Alert` | `error` or `success` with the right icon and ARIA role |
| `Spinner` | Centred loader with a label |
| `EmptyState` | Dashed-border placeholder with icon, title and body |
| `SectionTitle` | Heading plus optional subtitle |
| `Stat` | Label, icon and a large number |

`Field` is the one doing quiet work: it generates the `id`, points the label at the input and
links the hint through `aria-describedby`, so every form in the app is accessible without any
page remembering to do it.

---

## 10. Styling

Tailwind v4, configured in CSS rather than a JavaScript file. The whole design system is one
block in `src/index.css`:

```css
@theme {
  --color-ink-950: #08090c;
  --color-ink-900: #0d0f14;
  --color-ink-850: #12151c;
  --color-ink-800: #171b24;
  --color-ink-700: #232936;
  --color-ink-600: #333b4d;
  --color-volt-400: #c6f24e;
  --color-volt-500: #b0e02e;
  --color-volt-600: #8ab81c;
  --font-display: "Bebas Neue", "Impact", system-ui, sans-serif;
}
```

Two families only. **Ink** is six near-black greys used for background, cards, borders and
hover. **Volt** is the acid-green accent used for anything clickable that matters. Tailwind's
own `slate`, `red` and `amber` fill in text and alerts.

Restricting the palette this hard is what makes the app look designed rather than assembled. If
something is volt, it is the action.

Three component classes cover the repeated patterns: `.card`, `.input` and `.label`.

**Dark only.** `<html class="dark">` is hard-coded in `index.html`. There is no toggle and no
light theme, which is a product decision, not an unfinished one: a gym app is used in a dim
room, and one theme means one set of contrast choices to get right.

**Responsive** with Tailwind defaults: `sm` for stacked buttons becoming rows, `md` for the
switch between the mobile menu and the desktop nav, `lg` for the three-column plan grid and
two-column dashboards.

**Animation** is deliberately small: `.animate-rise` (0.45s fade and lift) for content
appearing, `.animate-pop` (0.22s scale) for the chat dialog and auth card, plus bouncing dots
while FitBot thinks and spinners on busy buttons. Backdrop blur on the header, cards and the
sticky analyst input.

---

## 11. Browser tests

```bash
cd frontend
npm run e2e          # run them
npm run e2e:report   # open the HTML report
```

**46 tests in 5 files**, driving real Chromium against both servers running.

| File | Tests | Covers |
| --- | --- | --- |
| `public.spec.ts` | 10 | Landing, packages, 404, route guards, signup and login |
| `staff.spec.ts` | 13 | Trainer desk, admin console, PDF ingest, cross-role flow |
| `fitbot.spec.ts` | 8 | The widget: prompts, in-chat sign-in, safety handoff |
| `member.spec.ts` | 7 | Membership card, programmes, booking, profile, sign out |
| `insights.spec.ts` | 8 | Analyst, advisor, Copilot tab, metric tables |

`helpers.ts` holds the shared pieces: `uniqueEmail()` for timestamped signups,
`signIn(page, who)` and `signOut(page)`, `openFitBot()` and `sendToFitBot()`. Trainer and
member credentials are the seeded demo ones; the admin comes from `E2E_ADMIN_EMAIL` and
`E2E_ADMIN_PASSWORD` so real credentials stay out of the repository.

```powershell
$env:E2E_ADMIN_EMAIL = "you@example.com"
$env:E2E_ADMIN_PASSWORD = "your-admin-password"
```

The most useful helper is the one that fails a passing test:

```ts
export function watchForClientErrors(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      const text = message.text();
      if (!text.includes("Download the React DevTools")) problems.push(`console: ${text}`);
    }
  });
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("response", (response) => {
    if (response.status() >= 500) {
      problems.push(`http ${response.status()}: ${response.url()}`);
    }
  });
  return problems;
}
```

A test that clicks the right buttons can still be hiding a React key warning or a 500 on a
background request. Tests call this at the start and assert `problems` is empty at the end, so
those get caught too.

Two deliberate config choices. **One worker**, because SQLite serialises writes and parallel
workers queue behind each other and time out rather than revealing real faults. And the AI
tests assert on **structure, not wording** — that a sign-in card appeared, that metric tables
rendered, that a briefing exists — because a free-tier model may be rate limited and its exact
words are not the contract.

The `staff.spec.ts` PDF ingest test expects `e2e/fixtures/protocol.pdf`, which is not committed.
Add any small PDF at that path to run it.

---

## 12. Build and deploy

```bash
npm run dev      # Vite dev server on 5173, /api proxied to 8000
npm run lint     # tsc --noEmit
npm run build    # tsc -b, then vite build into dist/
npm run preview  # serve the built files
```

`npm run build` type-checks before bundling, so a type error fails the build rather than
shipping.

Cloudflare Pages settings: framework preset Vite, build command `npm run build`, output
directory `dist`, root directory `frontend`, and one environment variable `VITE_API_URL`
pointing at the Render URL with no trailing slash.

One file makes client-side routing survive a refresh — `public/_redirects`:

```
/*  /index.html  200
```

React Router owns `/login` and `/dashboard`, but no such files exist on disk, so without this
rule refreshing on `/login` returns a CDN 404. Vite copies `public/` into `dist/`, so it ships
with every build.

---

## 13. Honest limitations

- **No streaming.** Chat and analyst replies arrive whole, so long answers feel slower than
  they would with a typed-out effect.
- **Token in `localStorage`.** Weaker against XSS than an httpOnly cookie. A knowing trade, as
  explained above.
- **No data-fetching library.** Each page does its own `useEffect` and `loading` state. That is
  fine at eight pages and would get repetitive at thirty; React Query would be the next step.
- **No ESLint or Prettier.** Type checking only.
- **No unit tests for components.** Confidence comes from Playwright end to end, which catches
  real breakage but gives slower and less precise feedback than component tests would.
- **`ChatAction.show_plans`** is in the types but has no UI branch yet, and
  `Profile.preferred_domains` is stored but not editable in the profile form.
- **No optimistic updates.** Booking a class waits for the server round trip before the button
  changes.
