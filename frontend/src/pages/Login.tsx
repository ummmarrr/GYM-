import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Lock } from "lucide-react";

import { homeFor, useAuth } from "../context/AuthContext";
import { useLanguage } from "../context/LanguageContext";
import { ApiError } from "../lib/api";
import { Alert, Button, Field } from "../components/ui";

const DEMO_LOGINS = [
  { role: "Member", email: "member-demo@example.com", password: "DemoMember123" },
  { role: "Trainer", email: "trainer-demo@example.com", password: "DemoTrainer123" },
  { role: "Admin", email: "admin-demo@example.com", password: "DemoAdmin123" },
];

export default function Login() {
  const { signIn } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const attempt = async (withEmail: string, withPassword: string) => {
    setBusy(true);
    setError("");
    try {
      const user = await signIn(withEmail, withPassword);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? homeFor(user.role), { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not sign in. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    void attempt(email, password);
  };

  const useDemo = (demo: (typeof DEMO_LOGINS)[number]) => {
    setEmail(demo.email);
    setPassword(demo.password);
    void attempt(demo.email, demo.password);
  };

  return (
    <div className="mx-auto flex max-w-md flex-col justify-center px-4 py-20 sm:px-6">
      <div className="card animate-rise p-8">
        <span className="grid h-11 w-11 place-items-center rounded-xl bg-volt-400/10 text-volt-400">
          <Lock className="h-5 w-5" aria-hidden />
        </span>
        <h1 className="mt-5 text-2xl font-bold tracking-tight text-white">
          {t("auth.signInTitle", "Welcome back")}
        </h1>
        <p className="mt-1.5 text-sm text-slate-400">
          {t("auth.signInSubtitle", "Sign in to your Master GYM account")}
        </p>

        <form onSubmit={submit} className="mt-7 space-y-4">
          <Field label={t("auth.email", "Email Address")}>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
              autoFocus
            />
          </Field>

          <Field label={t("auth.password", "Password")}>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete="current-password"
            />
          </Field>

          <Alert kind="error" message={error} />

          <Button type="submit" busy={busy} className="w-full">
            {t("auth.submitSignIn", "Sign In")}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-400">
          {t("auth.noAccount", "Don't have an account?")}{" "}
          <Link to="/join" className="font-semibold text-volt-400 hover:underline">
            {t("nav.join", "Join")}
          </Link>
        </p>

        <div className="mt-7 rounded-xl border border-ink-700 bg-ink-900/60 p-4">
          <p className="text-sm font-semibold text-white">{t("auth.demoAccounts", "Quick Demo Login")}</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {DEMO_LOGINS.map((demo) => (
              <Button
                key={demo.role}
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => useDemo(demo)}
              >
                {t(`nav.${demo.role.toLowerCase()}`, demo.role)}
              </Button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
