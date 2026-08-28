import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { homeFor, useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";
import { MEDIA } from "../lib/media";
import { Alert, Button, Field } from "../components/ui";

const DEMO_LOGINS = [
  { role: "Member", email: "member-demo@example.com", password: "DemoMember123" },
  { role: "Trainer", email: "trainer-demo@example.com", password: "DemoTrainer123" },
  { role: "Admin", email: "admin-demo@example.com", password: "DemoAdmin123" },
];

export default function Login() {
  const { signIn } = useAuth();
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
    <div className="relative isolate min-h-[calc(100vh-68px)] overflow-hidden">
      <img src={MEDIA.auth} alt="" className="absolute inset-0 -z-20 h-full w-full object-cover" />
      <div aria-hidden className="absolute inset-0 -z-10 bg-ink-950/80" />

      <div className="mx-auto flex max-w-md flex-col justify-center px-4 py-16 sm:px-6 sm:py-20">
        <div className="card animate-rise border-white/10 p-8">
          <p className="display text-3xl text-sand-50">
            MASTER<span className="text-volt-400">GYM</span>
          </p>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-sand-50">Welcome back</h1>
          <p className="mt-1.5 text-sm text-sand-300">
            Sign in to see your programme, package and classes.
          </p>

          <form onSubmit={submit} className="mt-7 space-y-4">
            <Field label="Email">
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

            <Field label="Password">
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
              Sign in
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-sand-300">
            New to Master GYM?{" "}
            <Link to="/join" className="font-semibold text-volt-400 hover:underline">
              Create an account
            </Link>
          </p>

          <div className="mt-7 border border-white/8 bg-ink-950/50 p-4">
            <p className="text-sm font-semibold text-sand-50">Just looking around?</p>
            <p className="mt-1 text-xs text-sand-300">
              Pick a role to sign in instantly. These shared logins can read everything and change
              nothing.
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {DEMO_LOGINS.map((demo) => (
                <Button
                  key={demo.role}
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => useDemo(demo)}
                >
                  {demo.role}
                </Button>
              ))}
            </div>
            <dl className="mt-3 space-y-1 text-[11px] text-sand-300/70">
              {DEMO_LOGINS.map((demo) => (
                <div key={demo.email} className="flex justify-between gap-2">
                  <dt>{demo.email}</dt>
                  <dd className="font-mono">{demo.password}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>

        <p className="mt-5 text-center text-xs text-sand-300/70">
          Admins sign in here on the web app only. FitBot never handles admin access.
        </p>
      </div>
    </div>
  );
}
