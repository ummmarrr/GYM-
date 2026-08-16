import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Dumbbell, Globe, LogOut, Menu, X } from "lucide-react";

import { homeFor, useAuth } from "../context/AuthContext";
import { useLanguage } from "../context/LanguageContext";
import { initials } from "../lib/format";
import { Button, ButtonLink } from "./ui";
import ColdStartBanner from "./ColdStartBanner";
import FitBotWidget from "./FitBotWidget";

function LanguageSelector() {
  const { language, setLanguage, languages } = useLanguage();

  return (
    <div className="relative inline-flex items-center">
      <label htmlFor="language-select" className="sr-only">
        Select Language
      </label>
      <Globe className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-volt-400" aria-hidden />
      <select
        id="language-select"
        value={language}
        onChange={(e) => setLanguage(e.target.value as any)}
        className="cursor-pointer appearance-none rounded-xl border border-ink-700 bg-ink-900 py-1.5 pl-8 pr-7 text-xs font-semibold text-white transition hover:border-volt-500/50 focus:border-volt-400 focus:outline-none focus:ring-1 focus:ring-volt-400"
      >
        {languages.map((l) => (
          <option key={l.code} value={l.code} className="bg-ink-900 text-white">
            {l.flag} {l.nativeName}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute right-2.5 text-[9px] text-slate-400">▼</span>
    </div>
  );
}

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
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const links = [
    { to: "/", label: t("nav.home", "Home"), end: true },
    { to: "/packages", label: t("nav.packages", "Packages") },
    ...(user ? [{ to: homeFor(user.role), label: t("nav.dashboard", "Dashboard") }] : []),
    ...(user && user.role === "admin" ? [{ to: "/admin/insights", label: t("nav.insights", "AI Insights") }] : []),
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
            <LanguageSelector />

            {user ? (
              <>
                <div className="flex items-center gap-2.5">
                  <span className="grid h-8 w-8 place-items-center rounded-full bg-ink-700 text-xs font-bold text-volt-400">
                    {initials(user.full_name)}
                  </span>
                  <div className="leading-tight">
                    <p className="text-sm font-medium text-white">{user.full_name}</p>
                    <p className="text-[11px] uppercase tracking-wider text-slate-500">
                      {t(`nav.${user.role}`, user.role)}
                    </p>
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
                  {t("nav.signIn", "Sign in")}
                </ButtonLink>
                <ButtonLink to="/join">{t("nav.join", "Join")}</ButtonLink>
              </>
            )}
          </div>

          <div className="flex items-center gap-2 md:hidden">
            <LanguageSelector />
            <button
              className="rounded-lg p-2 text-slate-300"
              onClick={() => setOpen((value) => !value)}
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
            >
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
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
                    {t("nav.signOut", "Sign out")}
                  </Button>
                ) : (
                  <>
                    <ButtonLink
                      to="/login"
                      variant="outline"
                      className="flex-1"
                      onClick={() => setOpen(false)}
                    >
                      {t("nav.signIn", "Sign in")}
                    </ButtonLink>
                    <ButtonLink to="/join" className="flex-1" onClick={() => setOpen(false)}>
                      {t("nav.join", "Join")}
                    </ButtonLink>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </header>

      <ColdStartBanner />

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-ink-800 bg-ink-950">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 py-8 text-sm text-slate-500 sm:flex-row sm:px-6">
          <Brand />
          <p>{t("footer.rights", "Master GYM. High-performance strength, yoga and combat sports.")}</p>
        </div>
      </footer>

      <FitBotWidget />
    </div>
  );
}
