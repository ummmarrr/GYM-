import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Lock } from "lucide-react";

import { homeFor, useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";
import { Alert, Button, Field } from "../components/ui";

export default function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await signIn(email, password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? homeFor(user.role), { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not sign in. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-md flex-col justify-center px-4 py-20 sm:px-6">
      <div className="card animate-rise p-8">
        <span className="grid h-11 w-11 place-items-center rounded-xl bg-volt-400/10 text-volt-400">
          <Lock className="h-5 w-5" aria-hidden />
        </span>
        <h1 className="mt-5 text-2xl font-bold tracking-tight text-white">Welcome back</h1>
        <p className="mt-1.5 text-sm text-slate-400">
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

        <p className="mt-6 text-center text-sm text-slate-400">
          New to Master GYM?{" "}
          <Link to="/join" className="font-semibold text-volt-400 hover:underline">
            Create an account
          </Link>
        </p>
      </div>

      <p className="mt-5 text-center text-xs text-slate-500">
        Admins sign in here on the web app only. FitBot never handles admin access.
      </p>
    </div>
  );
}
