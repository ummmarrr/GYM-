import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Sparkles } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { useLanguage } from "../context/LanguageContext";
import { api, ApiError } from "../lib/api";
import type { Plan } from "../lib/api";
import { quotaLabel, rupees } from "../lib/format";
import { Alert, Badge, Button, Spinner } from "../components/ui";

export default function Packages() {
  const { user, entitlements, refresh } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();

  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    api
      .plans()
      .then(setPlans)
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.message : "Could not load packages."),
      );
  }, []);

  const choose = async (plan: Plan) => {
    if (!user) {
      navigate("/join", { state: { planId: plan.id } });
      return;
    }
    setBusyId(plan.id);
    setError("");
    setSuccess("");
    try {
      const result = await api.buyPlan(plan.id);
      setSuccess(result.message);
      await refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not activate that package.");
    } finally {
      setBusyId(null);
    }
  };

  const perks = (plan: Plan): string[] => {
    const disciplines = plan.allowed_disciplines
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    return [
      `${disciplines.map((item) => item.toUpperCase()).join(" + ")} access`,
      `Classes: ${quotaLabel(plan.monthly_class_quota)}`,
      plan.personalised_programme
        ? t("packages.personalised", "Personalized workout & diet programme")
        : "General coaching from FitBot",
      plan.priority_support
        ? t("packages.priority", "Priority trainer support")
        : "Standard support",
      `${plan.duration_days} ${t("packages.days", "days")}`,
    ];
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <div className="mx-auto max-w-2xl text-center">
        <h1 className="text-4xl font-extrabold tracking-tight text-white">
          {t("packages.title", "Simple, transparent packages")}
        </h1>
        <p className="mt-3 text-slate-400">
          {t("packages.subtitle", "Choose the tier that matches your goals. Every package comes with gym floor access and 24/7 FitBot assistance.")}
        </p>
        {entitlements?.has_active_membership && (
          <p className="mt-4 text-sm text-volt-400">
            You are on {entitlements.plan_name} with {entitlements.days_remaining} {t("member.daysLeft", "days left")}.
          </p>
        )}
      </div>

      <div className="mx-auto mt-8 max-w-xl space-y-3">
        <Alert kind="error" message={error} />
        <Alert kind="success" message={success} />
      </div>

      {!plans ? (
        <Spinner label="Loading packages" />
      ) : (
        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {plans.map((plan) => {
            const featured = plan.tier === "performance";
            const current = entitlements?.plan_name === plan.name;
            return (
              <div
                key={plan.id}
                className={`card relative flex flex-col p-7 transition ${
                  featured ? "border-volt-500/50 ring-1 ring-volt-500/20" : "hover:border-ink-600"
                }`}
              >
                {featured && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <Badge tone="volt">
                      <Sparkles className="mr-1 h-3 w-3" aria-hidden />
                      Popular
                    </Badge>
                  </span>
                )}

                <h2 className="text-xl font-bold text-white">{plan.name}</h2>
                <p className="mt-1.5 min-h-[3rem] text-sm leading-relaxed text-slate-400">
                  {plan.description}
                </p>

                <p className="mt-5 text-4xl font-extrabold tracking-tight text-white">
                  {rupees(plan.price_paise)}
                </p>
                <p className="text-sm text-slate-500">
                  for {plan.duration_days} {t("packages.days", "days")}
                </p>

                <ul className="mt-6 flex-1 space-y-2.5">
                  {perks(plan).map((perk) => (
                    <li key={perk} className="flex items-start gap-2.5 text-sm text-slate-300">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-volt-400" aria-hidden />
                      {perk}
                    </li>
                  ))}
                </ul>

                <Button
                  className="mt-7 w-full"
                  variant={featured ? "primary" : "outline"}
                  busy={busyId === plan.id}
                  disabled={current}
                  onClick={() => void choose(plan)}
                >
                  {current ? "Active Plan" : user ? t("packages.getStarted", "Get Started") : t("nav.join", "Join")}
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
