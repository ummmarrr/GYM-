import type { ButtonHTMLAttributes, ReactElement, ReactNode } from "react";
import { cloneElement, isValidElement, useId } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

type Variant = "primary" | "ghost" | "outline" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-volt-400 text-ink-950 hover:bg-volt-500 focus-visible:outline-volt-400",
  ghost: "text-slate-300 hover:bg-ink-800 hover:text-white focus-visible:outline-ink-600",
  outline:
    "border border-ink-600 text-slate-200 hover:border-volt-500/60 hover:text-white focus-visible:outline-volt-400",
  danger: "border border-red-500/40 text-red-300 hover:bg-red-500/10 focus-visible:outline-red-500",
};

const BASE = `inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold
  transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
  disabled:cursor-not-allowed disabled:opacity-50`;

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  busy?: boolean;
}

export function Button({
  variant = "primary",
  busy = false,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={`${BASE} ${VARIANTS[variant]} ${className}`}
    >
      {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

/**
 * A navigation control that looks like a button. Nesting a <button> inside a <Link> would
 * produce invalid, doubly-focusable markup, so anything that navigates uses this instead.
 */
export function ButtonLink({
  to,
  variant = "primary",
  className = "",
  children,
  onClick,
}: {
  to: string;
  variant?: Variant;
  className?: string;
  children: ReactNode;
  onClick?: () => void;
}) {
  return (
    <Link to={to} onClick={onClick} className={`${BASE} ${VARIANTS[variant]} ${className}`}>
      {children}
    </Link>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "volt" | "warn" | "danger";
}) {
  const tones = {
    neutral: "border-ink-600 bg-ink-800 text-slate-300",
    volt: "border-volt-500/40 bg-volt-500/10 text-volt-400",
    warn: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    danger: "border-red-500/40 bg-red-500/10 text-red-300",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

interface ControlProps {
  id?: string;
  "aria-describedby"?: string;
}

/**
 * Wires the label to whichever control is passed in so clicking the label focuses it and
 * screen readers announce it. The caller may still supply its own id, which wins.
 */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  const generatedId = useId();
  const controlId = isValidElement<ControlProps>(children)
    ? (children.props.id ?? generatedId)
    : generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;

  const control = isValidElement<ControlProps>(children)
    ? cloneElement(children as ReactElement<ControlProps>, {
        id: controlId,
        "aria-describedby": children.props["aria-describedby"] ?? hintId,
      })
    : children;

  return (
    <div>
      <label className="label" htmlFor={controlId}>
        {label}
      </label>
      {control}
      {hint && (
        <p id={hintId} className="mt-1.5 text-xs text-slate-500">
          {hint}
        </p>
      )}
    </div>
  );
}

export function Alert({ kind, message }: { kind: "error" | "success"; message: string }) {
  if (!message) return null;
  const isError = kind === "error";
  const Icon = isError ? AlertCircle : CheckCircle2;
  return (
    <div
      role={isError ? "alert" : "status"}
      className={`flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-sm ${
        isError
          ? "border-red-500/30 bg-red-500/10 text-red-200"
          : "border-volt-500/30 bg-volt-500/10 text-volt-400"
      }`}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 py-16 text-sm text-slate-400">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function EmptyState({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-ink-700 px-6 py-14 text-center">
      <div className="text-slate-600">{icon}</div>
      <p className="font-semibold text-slate-300">{title}</p>
      <p className="max-w-sm text-sm text-slate-500">{body}</p>
    </div>
  );
}

export function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-5">
      <h2 className="text-xl font-bold tracking-tight text-white">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
    </div>
  );
}

export function Stat({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | number;
  icon: ReactNode;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</p>
        <span className="text-volt-400">{icon}</span>
      </div>
      <p className="mt-2 text-3xl font-bold tracking-tight text-white">{value}</p>
    </div>
  );
}
