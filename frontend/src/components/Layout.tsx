import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Dumbbell, LogOut, Menu, X } from "lucide-react";

import { homeFor, useAuth } from "../context/AuthContext";
import { initials } from "../lib/format";
import { Button, ButtonLink } from "./ui";
import FitBotWidget from "./FitBotWidget";

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-volt-400 text-ink-950">
        <Dumbbell className="h-5 w-5" aria-hidden />
      </span>
      <span className="text-lg font-extrabold uppercase tracking-[0.18em] text-white">
        Master<span className="text-volt-400">GYM</span>
      </span>
    </Link>
  );
}

export default function Layout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const links = [
    { to: "/", label: "Home", end: true },
    { to: "/packages", label: "Packages" },
    ...(user ? [{ to: homeFor(user.role), label: "Dashboard" }] : []),
  ];

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm font-medium transition ${
      isActive ? "text-volt-400" : "text-slate-300 hover:text-white"
    }`;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-ink-800 bg-ink-950/85 backdrop-blur-xl">
        <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Brand />

          <div className="hidden items-center gap-1 md:flex">
            {links.map((link) => (
              <NavLink key={link.to} to={link.to} end={link.end} className={linkClass}>
                {link.label}
              </NavLink>
            ))}
          </div>

          <div className="hidden items-center gap-3 md:flex">
            {user ? (
              <>
                <div className="flex items-center gap-2.5">
                  <span className="grid h-8 w-8 place-items-center rounded-full bg-ink-700 text-xs font-bold text-volt-400">
                    {initials(user.full_name)}
                  </span>
                  <div className="leading-tight">
                    <p className="text-sm font-medium text-white">{user.full_name}</p>
                    <p className="text-[11px] uppercase tracking-wider text-slate-500">{user.role}</p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  onClick={() => {
                    signOut();
                    navigate("/");
                  }}
                  aria-label="Sign out"
                >
                  <LogOut className="h-4 w-4" aria-hidden />
                </Button>
              </>
            ) : (
              <>
                <ButtonLink to="/login" variant="ghost">
                  Sign in
                </ButtonLink>
                <ButtonLink to="/join">Join now</ButtonLink>
              </>
            )}
          </div>

          <button
            className="rounded-lg p-2 text-slate-300 md:hidden"
            onClick={() => setOpen((value) => !value)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </nav>

        {open && (
          <div className="border-t border-ink-800 px-4 py-3 md:hidden">
            <div className="flex flex-col gap-1">
              {links.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.end}
                  className={linkClass}
                  onClick={() => setOpen(false)}
                >
                  {link.label}
                </NavLink>
              ))}
              <div className="mt-3 flex gap-2">
                {user ? (
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => {
                      signOut();
                      setOpen(false);
                      navigate("/");
                    }}
                  >
                    Sign out
                  </Button>
                ) : (
                  <>
                    <ButtonLink
                      to="/login"
                      variant="outline"
                      className="flex-1"
                      onClick={() => setOpen(false)}
                    >
                      Sign in
                    </ButtonLink>
                    <ButtonLink to="/join" className="flex-1" onClick={() => setOpen(false)}>
                      Join now
                    </ButtonLink>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-ink-800 bg-ink-950">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 py-8 text-sm text-slate-500 sm:flex-row sm:px-6">
          <Brand />
          <p>Strength · Yoga · MMA — coached by FitBot and real trainers.</p>
        </div>
      </footer>

      <FitBotWidget />
    </div>
  );
}
