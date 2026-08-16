import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { UserPlus } from "lucide-react";

import { homeFor, useAuth } from "../context/AuthContext";
import { useLanguage } from "../context/LanguageContext";
import { api, ApiError } from "../lib/api";
import { Alert, Button, Field } from "../components/ui";

export default function Join() {
  const { signUp } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();
  const preselectedPlan = (location.state as { planId?: string } | null)?.planId;

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await signUp({
        email,
        full_name: fullName,
        password,
        phone: phone || undefined,
      });
      if (preselectedPlan) {
        await api.buyPlan(preselectedPlan).catch(() => undefined);
      }
      navigate(homeFor(user.role), { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create your account.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-md flex-col justify-center px-4 py-20 sm:px-6">
      <div className="card animate-rise p-8">
        <span className="grid h-11 w-11 place-items-center rounded-xl bg-volt-400/10 text-volt-400">
          <UserPlus className="h-5 w-5" aria-hidden />
        </span>
        <h1 className="mt-5 text-2xl font-bold tracking-tight text-white">
          {t("auth.signUpTitle", "Create your account")}
        </h1>
        <p className="mt-1.5 text-sm text-slate-400">
          {t("auth.signUpSubtitle", "Join Master GYM and start your transformation")}
        </p>

        <form onSubmit={submit} className="mt-7 space-y-4">
          <Field label={t("auth.fullName", "Full Name")}>
            <input
              className="input"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
              minLength={2}
              autoComplete="name"
              autoFocus
            />
          </Field>

          <Field label={t("auth.email", "Email Address")}>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
            />
          </Field>

          <Field label={t("auth.phone", "Phone Number (optional)")}>
            <input
              className="input"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              autoComplete="tel"
            />
          </Field>

          <Field label={t("auth.password", "Password")}>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
            />
          </Field>

          <Alert kind="error" message={error} />

          <Button type="submit" busy={busy} className="w-full">
            {t("auth.submitSignUp", "Create Account")}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-400">
          {t("auth.hasAccount", "Already have an account?")}{" "}
          <Link to="/login" className="font-semibold text-volt-400 hover:underline">
            {t("nav.signIn", "Sign in")}
          </Link>
        </p>
      </div>
    </div>
  );
}
