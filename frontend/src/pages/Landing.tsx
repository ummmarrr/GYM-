import {
  ArrowRight,
  Bot,
  Dumbbell,
  Flower2,
  Swords,
} from "lucide-react";

import { homeFor, useAuth } from "../context/AuthContext";
import { useLanguage } from "../context/LanguageContext";
import { Badge, ButtonLink } from "../components/ui";

export default function Landing() {
  const { user } = useAuth();
  const { t } = useLanguage();

  const disciplines = [
    {
      icon: Dumbbell,
      title: t("landing.feature1Title", "Strength & Conditioning"),
      body: t(
        "landing.feature1Desc",
        "State-of-the-art free weights, Olympic lifting platforms, and pin-loaded machines for optimal muscle hypertrophy and raw power.",
      ),
    },
    {
      icon: Flower2,
      title: t("landing.feature2Title", "Yoga & Mobility"),
      body: t(
        "landing.feature2Desc",
        "Calm, dedicated studio with experienced gurus for Asana mastery, breath control, flexibility, and core stability.",
      ),
    },
    {
      icon: Swords,
      title: t("landing.feature3Title", "MMA & Combat Arena"),
      body: t(
        "landing.feature3Desc",
        "Full-size cage, heavy bags, and tatami mats for boxing, Muay Thai striking, wrestling, and Brazilian Jiu-Jitsu.",
      ),
    },
  ];

  const stats = [
    { value: t("landing.stat1Val", "3 Disciplines"), label: t("landing.stat1Lbl", "Gym, Yoga & MMA Combat") },
    { value: t("landing.stat2Val", "24/7 AI Coach"), label: t("landing.stat2Lbl", "Personalized to your package") },
    { value: t("landing.stat3Val", "Expert Staff"), label: t("landing.stat3Lbl", "Custom diet & workout plans") },
  ];

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
              {t("landing.badge", "Smart Gym & AI Coaching")}
            </Badge>
          </div>

          <h1 className="animate-rise mt-6 text-5xl font-extrabold leading-[1.05] tracking-tight text-white sm:text-7xl">
            {t("landing.heroTitle1", "Train with precision.")}
            <br />
            <span className="text-volt-400">{t("landing.heroTitle2", "Coached by intelligence.")}</span>
          </h1>

          <p className="animate-rise mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-slate-400">
            {t(
              "landing.heroSubtitle",
              "Elite equipment, certified trainers, and FitBot — your personalized 24/7 AI coach trained on our official gym curricula.",
            )}
          </p>

          <div className="animate-rise mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            {user ? (
              <ButtonLink to={homeFor(user.role)} className="px-6 py-3">
                {t("nav.dashboard", "Dashboard")}
                <ArrowRight className="h-4 w-4" aria-hidden />
              </ButtonLink>
            ) : (
              <>
                <ButtonLink to="/packages" className="px-6 py-3">
                  {t("landing.ctaJoin", "Explore Packages")}
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </ButtonLink>
                <ButtonLink to="/join" variant="outline" className="px-6 py-3">
                  {t("nav.join", "Join")}
                </ButtonLink>
              </>
            )}
          </div>

          <div className="mt-14 grid grid-cols-1 gap-4 border-t border-ink-800 pt-8 sm:grid-cols-3">
            {stats.map((s) => (
              <div key={s.value} className="text-center">
                <p className="text-2xl font-extrabold text-volt-400">{s.value}</p>
                <p className="mt-1 text-xs text-slate-400">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y border-ink-800 bg-ink-900/50">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-16 sm:px-6 md:grid-cols-3">
          {disciplines.map(({ icon: Icon, title, body }) => (
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
    </>
  );
}
