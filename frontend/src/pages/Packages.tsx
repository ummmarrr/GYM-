import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import type { Plan } from "../lib/api";
import { quotaLabel, rupees } from "../lib/format";
import { Alert, Badge, Button, Spinner } from "../components/ui";

function perks(plan: Plan): string[] {
  const disciplines = plan.allowed_disciplines
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return [
    `${disciplines.map((item) => item.toUpperCase()).join(" + ")} access`,
    `Classes: ${quotaLabel(plan.monthly_class_quota)}`,
    plan.personalised_programme
      ? "Trainer-written workout and diet plan"
      : "General coaching from FitBot",
    plan.priority_support ? "Priority support" : "Standard support",
    `${plan.duration_days} days validity`,
  ];
}

export default function Packages() {
  const { user, entitlements, refresh } = useAuth();
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

  return (
    <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
      <div className="max-w-xl">
        <h1 className="display text-[clamp(2.75rem,6vw,4rem)] text-sand-50">Packages</h1>
        <p className="mt-3 text-sand-300">
          Every limit here is enforced by the server, so what you buy is exactly what you get.
        </p>
        {entitlements?.has_active_membership && (
          <p className="mt-4 text-sm text-volt-400">
            You are on {entitlements.plan_name} with {entitlements.days_remaining} days left.
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
        <div className="mt-12 grid gap-4 lg:grid-cols-3">
          {plans.map((plan) => {
            const featured = plan.tier === "performance";
            const current = entitlements?.plan_name === plan.name;
            return (
              <div
                key={plan.id}
                className={`relative flex flex-col border p-7 transition ${
                  featured
                    ? "border-volt-400/45 bg-gradient-to-b from-volt-400/10 to-ink-900"
                    : "border-white/8 bg-ink-900 hover:border-white/16"
                }`}
              >
                {featured && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <Badge tone="volt">
                      <Sparkles className="mr-1 h-3 w-3" aria-hidden />
                      Most popular
                    </Badge>
                  </span>
                )}

                <h2 className="display text-[1.75rem] text-sand-50">{plan.name}</h2>
                <p className="mt-2 min-h-[3rem] text-sm leading-relaxed text-sand-300">
                  {plan.description}
                </p>

                <p className="mt-5 text-3xl font-semibold tracking-tight text-sand-50">
                  {rupees(plan.price_paise)}
                </p>
                <p className="text-sm text-sand-300">for {plan.duration_days} days</p>

                <ul className="mt-6 flex-1 space-y-2.5">
                  {perks(plan).map((perk) => (
                    <li key={perk} className="flex items-start gap-2.5 text-sm text-sand-300">
                      <span className="text-volt-400" aria-hidden>
                        —
                      </span>
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
                  {current ? "Your current package" : user ? "Activate" : "Join and choose"}
                </Button>
              </div>
            );
          })}
        </div>
      )}

      <p className="mt-10 text-center text-xs text-sand-300/70">
        Payments are simulated in this build. No card details are collected anywhere in the app.
      </p>
    </div>
  );
}
