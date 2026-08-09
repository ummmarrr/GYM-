export function rupees(paise: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(paise / 100);
}

/** Timestamps arrive from the API as naive UTC, which JS would otherwise read as local time. */
const NAIVE_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/;

export function parseApiDate(value: string): Date {
  return new Date(NAIVE_DATETIME.test(value) ? `${value}Z` : value);
}

export function longDate(value: string | null): string {
  if (!value) return "—";
  return parseApiDate(value).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function classTime(value: string): string {
  return parseApiDate(value).toLocaleString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function quotaLabel(quota: number): string {
  if (quota < 0) return "Unlimited";
  if (quota === 0) return "None";
  return `${quota} / month`;
}

export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
