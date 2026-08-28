import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { homeFor, useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import { MEDIA } from "../lib/media";
import { Alert, Button, Field } from "../components/ui";

export default function Join() {
  const { signUp } = useAuth();
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
    <div className="relative isolate min-h-[calc(100vh-68px)] overflow-hidden">
      <img
        src={MEDIA.strength}
        alt=""
        className="absolute inset-0 -z-20 h-full w-full object-cover"
      />
      <div aria-hidden className="absolute inset-0 -z-10 bg-ink-950/82" />

      <div className="mx-auto flex max-w-md flex-col justify-center px-4 py-16 sm:px-6 sm:py-20">
        <div className="card animate-rise border-white/10 p-8">
          <p className="display text-3xl text-sand-50">
            MASTER<span className="text-volt-400">GYM</span>
          </p>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-sand-50">
            Join Master GYM
          </h1>
          <p className="mt-1.5 text-sm text-sand-300">
            One minute to set up. You can pick a package right after.
          </p>

          <form onSubmit={submit} className="mt-7 space-y-4">
            <Field label="Full name">
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

            <Field label="Email">
              <input
                className="input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
              />
            </Field>

            <Field label="Phone" hint="Optional, used only for class reminders.">
              <input
                className="input"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                autoComplete="tel"
              />
            </Field>

            <Field label="Password" hint="At least 8 characters.">
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
              Create account
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-sand-300">
            Already a member?{" "}
            <Link to="/login" className="font-semibold text-volt-400 hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
