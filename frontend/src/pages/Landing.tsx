import { ArrowRight } from "lucide-react";

import { homeFor, useAuth } from "../context/AuthContext";
import { MEDIA } from "../lib/media";
import { ButtonLink } from "../components/ui";

const DISCIPLINES = [
  {
    title: "Strength",
    body: "Progressive overload with programmes written by your assigned trainer.",
    image: MEDIA.strength,
  },
  {
    title: "Yoga",
    body: "Mobility and breathwork that recover what heavy training takes.",
    image: MEDIA.yoga,
  },
  {
    title: "MMA",
    body: "Striking and grappling fundamentals — unlocked by higher packages.",
    image: MEDIA.mma,
  },
];

const FITBOT_POINTS = [
  {
    title: "Knows your entitlements",
    body: "Quota, expiry, and which disciplines are locked until you upgrade.",
  },
  {
    title: "Reads gym knowledge",
    body: "Agentic retrieval over PDFs filtered to the caller’s package.",
  },
  {
    title: "Safe by default",
    body: "No medical guesses. Never asks for a password.",
  },
];

export default function Landing() {
  const { user } = useAuth();

  return (
    <>
      <section className="relative isolate flex min-h-[calc(100vh-68px)] items-end overflow-hidden">
        <img
          src={MEDIA.hero}
          alt=""
          className="absolute inset-0 -z-20 h-full w-full object-cover"
        />
        <div
          aria-hidden
          className="absolute inset-0 -z-10 bg-gradient-to-t from-ink-950 via-ink-950/75 to-ink-950/35"
        />
        <div
          aria-hidden
          className="absolute inset-0 -z-10 bg-[radial-gradient(60%_50%_at_75%_40%,rgba(198,242,78,0.12),transparent_60%)]"
        />

        <div className="relative mx-auto w-full max-w-6xl px-4 pb-20 pt-24 sm:px-6 sm:pb-24">
          <div className="animate-rise max-w-2xl">
            <p className="text-xs uppercase tracking-[0.22em] text-sand-300">
              Strength · Yoga · MMA
            </p>
            <p className="display mt-4 text-[clamp(4rem,12vw,7.5rem)] text-sand-50">
              MASTER<span className="text-volt-400">GYM</span>
            </p>
            <h1 className="mt-3 max-w-[14ch] text-[clamp(1.75rem,4vw,2.6rem)] font-semibold leading-[1.15] tracking-tight text-sand-50">
              Train with intent. Not guesswork.
            </h1>
            <p className="mt-4 max-w-[38ch] text-base leading-relaxed text-sand-300 sm:text-lg">
              Real coaches, live class seats, and FitBot — an AI coach that knows your package,
              your programme, and your limits.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
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

            <p className="mt-5 text-sm text-sand-300">
              Or tap <span className="font-semibold text-volt-400">Ask FitBot</span> in the corner —
              no account needed to try it.
            </p>
          </div>
        </div>
      </section>

      <section className="px-4 py-20 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-6xl">
          <div className="max-w-xl">
            <h2 className="display text-[clamp(2.25rem,5vw,3.5rem)] text-sand-50">
              Three disciplines. One membership.
            </h2>
            <p className="mt-3 text-sand-300">
              Mapped to what your package unlocks on the server — not just pretty labels.
            </p>
          </div>

          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {DISCIPLINES.map((item) => (
              <article
                key={item.title}
                className="group relative min-h-[320px] overflow-hidden border border-white/8 bg-ink-900"
              >
                <img
                  src={item.image}
                  alt=""
                  className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-105"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-ink-950 via-ink-950/55 to-ink-950/10" />
                <div className="absolute inset-x-0 bottom-0 p-6">
                  <h3 className="display text-[2.1rem] text-sand-50">{item.title}</h3>
                  <p className="mt-2 max-w-[28ch] text-sm leading-relaxed text-sand-300">
                    {item.body}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y border-white/8 bg-ink-900/60 px-4 py-20 sm:px-6 sm:py-24">
        <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <h2 className="display text-[clamp(2.25rem,5vw,3.5rem)] text-sand-50">
              FitBot answers when the floor is empty.
            </h2>
            <p className="mt-3 max-w-lg text-sand-300">
              Tool-calling coach backed by your gym docs, package filters, and live pricing —
              the same APIs your app already uses.
            </p>
            <div className="mt-8 space-y-5">
              {FITBOT_POINTS.map((point) => (
                <article key={point.title} className="border-b border-white/8 pb-5">
                  <h3 className="text-[15px] font-semibold text-sand-50">{point.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-sand-300">{point.body}</p>
                </article>
              ))}
            </div>
          </div>

          <div
            className="flex min-h-[280px] flex-col gap-3.5 border border-white/8 bg-white/[0.02] p-5"
            aria-label="FitBot sample conversation"
          >
            <div className="ml-auto max-w-[90%] rounded-2xl rounded-br-sm bg-white/6 px-3.5 py-3 text-sm leading-relaxed text-sand-50">
              What time is evening yoga, and can I book on Starter?
            </div>
            <div className="max-w-[90%] rounded-2xl rounded-bl-sm border border-volt-400/20 bg-volt-400/8 px-3.5 py-3 text-sm leading-relaxed text-sand-50">
              Evening yoga is 7:00–8:00 PM. Starter includes yoga seats this month — I can open
              booking once you sign in. Want the full timetable?
            </div>
            <div className="ml-auto max-w-[90%] rounded-2xl rounded-br-sm bg-white/6 px-3.5 py-3 text-sm leading-relaxed text-sand-50">
              Yes, and what’s locked on Starter?
            </div>
            <div className="max-w-[90%] rounded-2xl rounded-bl-sm border border-volt-400/20 bg-volt-400/8 px-3.5 py-3 text-sm leading-relaxed text-sand-50">
              MMA content stays locked until Complete. Strength + Yoga manuals are readable now.
            </div>
          </div>
        </div>
      </section>

      <section className="px-4 py-24 text-center sm:px-6 sm:py-28">
        <div className="mx-auto max-w-3xl">
          <h2 className="display mx-auto max-w-[16ch] text-[clamp(2.5rem,7vw,4.5rem)] text-sand-50">
            Your first session is the hardest.
          </h2>
          <p className="mx-auto mt-4 max-w-[36ch] text-sand-300">
            Pick a package, tell FitBot your goal, and walk in knowing the plan.
          </p>
          <ButtonLink
            to={user ? homeFor(user.role) : "/join"}
            className="mt-8 px-6 py-3"
          >
            {user ? "Open my dashboard" : "Create my account"}
            <ArrowRight className="h-4 w-4" aria-hidden />
          </ButtonLink>
        </div>
      </section>
    </>
  );
}
