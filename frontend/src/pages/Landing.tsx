import {
  ArrowRight,
  Bot,
  CalendarCheck,
  Dumbbell,
  Flower2,
  ShieldCheck,
  Swords,
  Users,
} from "lucide-react";

import { homeFor, useAuth } from "../context/AuthContext";
import { Badge, ButtonLink } from "../components/ui";

const DISCIPLINES = [
  {
    icon: Dumbbell,
    title: "Strength & Conditioning",
    body: "Progressive overload built around your lifts, your schedule and the equipment you actually have.",
  },
  {
    icon: Flower2,
    title: "Yoga & Mobility",
    body: "Guided asana, breathwork and mobility work that undoes what a desk job does to your hips.",
  },
  {
    icon: Swords,
    title: "MMA & Striking",
    body: "Boxing, muay thai and grappling fundamentals, drilled safely with qualified coaches.",
  },
];

const FEATURES = [
  {
    icon: Bot,
    title: "FitBot answers instantly",
    body: "A coach in your pocket that reads the gym's own manuals before it answers, so advice matches what our trainers teach.",
  },
  {
    icon: Users,
    title: "A real trainer behind it",
    body: "Your assigned trainer writes your workout and diet programme. FitBot explains and adapts it day to day.",
  },
  {
    icon: CalendarCheck,
    title: "Book classes in seconds",
    body: "Live seat counts across strength, yoga and MMA sessions, with your package limits applied automatically.",
  },
  {
    icon: ShieldCheck,
    title: "Safety comes first",
    body: "Anything medical is escalated to a human, never guessed at. FitBot will never ask for your password.",
  },
];

export default function Landing() {
  const { user } = useAuth();

  return (
    <>
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_0%,rgba(198,242,78,0.14),transparent_70%)]"
        />
        <div className="relative mx-auto max-w-6xl px-4 py-24 text-center sm:px-6 sm:py-32">
          <div className="animate-rise">
            <Badge tone="volt">
              <Bot className="mr-1.5 h-3 w-3" aria-hidden />
              Now with FitBot, your AI coach
            </Badge>
          </div>

          <h1 className="animate-rise mt-6 text-5xl font-extrabold leading-[1.05] tracking-tight text-white sm:text-7xl">
            Train with intent.
            <br />
            <span className="text-volt-400">Not guesswork.</span>
          </h1>

          <p className="animate-rise mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-slate-400">
            Master GYM combines real coaches with FitBot — an assistant that knows your package,
            your programme and your limits, and answers at 5am when nobody else will.
          </p>

          <div className="animate-rise mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            {user ? (
              <ButtonLink to={homeFor(user.role)} className="px-6 py-3">
                Go to my dashboard
                <ArrowRight className="h-4 w-4" aria-hidden />
              </ButtonLink>
            ) : (
              <>
                <ButtonLink to="/join" className="px-6 py-3">
                  Start training
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </ButtonLink>
                <ButtonLink to="/packages" variant="outline" className="px-6 py-3">
                  See packages
                </ButtonLink>
              </>
            )}
          </div>

          <p className="mt-5 text-sm text-slate-500">
            Or tap <span className="font-semibold text-volt-400">Ask FitBot</span> in the corner —
            no account needed to try it.
          </p>
        </div>
      </section>

      <section className="border-y border-ink-800 bg-ink-900/50">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-16 sm:px-6 md:grid-cols-3">
          {DISCIPLINES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="card p-6 transition hover:border-volt-500/40">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-volt-400/10 text-volt-400">
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <h3 className="mt-4 text-lg font-bold text-white">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
            A gym that answers back
          </h2>
          <p className="mt-3 text-slate-400">
            Everything below is enforced on our server, not just shown in the app.
          </p>
        </div>

        <div className="mt-12 grid gap-6 sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="flex gap-4">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-ink-700 bg-ink-850 text-volt-400">
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <div>
                <h3 className="font-bold text-white">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-ink-800">
        <div className="mx-auto max-w-4xl px-4 py-20 text-center sm:px-6">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
            Your first session is the hardest.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-slate-400">
            Pick a package, tell FitBot your goal, and walk in on day one already knowing exactly
            what you are doing.
          </p>
          <ButtonLink to={user ? homeFor(user.role) : "/join"} className="mt-8 px-6 py-3">
            {user ? "Open my dashboard" : "Create my account"}
            <ArrowRight className="h-4 w-4" aria-hidden />
          </ButtonLink>
        </div>
      </section>
    </>
  );
}
