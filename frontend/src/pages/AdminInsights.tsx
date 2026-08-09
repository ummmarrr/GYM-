import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUp,
  BarChart3,
  ChevronLeft,
  Compass,
  Lightbulb,
  RefreshCw,
  ShieldCheck,
  Table2,
} from "lucide-react";

import { api, ApiError } from "../lib/api";
import type { AdvisorReport, MetricTable, Priority, Recommendation } from "../lib/api";
import { Alert, Badge, Button, SectionTitle, Spinner } from "../components/ui";

const SUGGESTIONS = [
  "How much revenue have we made?",
  "Whose membership expires soon?",
  "Are our classes filling up?",
  "Which members have gone quiet?",
  "How is each trainer loaded?",
];

const PRIORITY_TONE: Record<Priority, "danger" | "warn" | "neutral"> = {
  high: "danger",
  medium: "warn",
  low: "neutral",
};

interface Turn {
  id: number;
  question: string;
  answer: string;
  metrics: MetricTable[];
}

function MetricGrid({ metric }: { metric: MetricTable }) {
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-900">
      <div className="border-b border-ink-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <Table2 className="h-3.5 w-3.5 text-volt-400" aria-hidden />
          <p className="text-sm font-semibold text-white">{metric.title}</p>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate-400">{metric.headline}</p>
      </div>

      {metric.rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                {metric.columns.map((column) => (
                  <th key={column} className="px-4 py-2.5 font-medium">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {metric.rows.map((row, index) => (
                <tr key={index} className="text-slate-300">
                  {metric.columns.map((column) => (
                    <td key={column} className="px-4 py-2.5">
                      {row[column] ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RecommendationCard({ item }: { item: Recommendation }) {
  return (
    <article className="card p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={PRIORITY_TONE[item.priority]}>{item.priority} priority</Badge>
        <Badge>{item.category}</Badge>
      </div>
      <h3 className="mt-3 font-bold text-white">{item.title}</h3>

      <dl className="mt-3 space-y-2 text-sm">
        <div>
          <dt className="text-xs uppercase tracking-wider text-slate-500">Evidence</dt>
          <dd className="mt-0.5 leading-relaxed text-slate-300">{item.evidence}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-slate-500">Do this</dt>
          <dd className="mt-0.5 leading-relaxed text-volt-400">{item.action}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-slate-500">Why it matters</dt>
          <dd className="mt-0.5 leading-relaxed text-slate-400">{item.impact}</dd>
        </div>
      </dl>
    </article>
  );
}

export default function AdminInsights() {
  const [tab, setTab] = useState<"analyst" | "advisor">("analyst");

  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);

  const [report, setReport] = useState<AdvisorReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  const [metrics, setMetrics] = useState<MetricTable[] | null>(null);

  useEffect(() => {
    api
      .metrics()
      .then(setMetrics)
      .catch(() => setMetrics([]));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, asking]);

  const loadReport = useCallback(async () => {
    setLoadingReport(true);
    setError("");
    try {
      setReport(await api.advisorReport());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not build the report.");
    } finally {
      setLoadingReport(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "advisor" && !report && !loadingReport) void loadReport();
  }, [tab, report, loadingReport, loadReport]);

  const ask = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || asking) return;
    setDraft("");
    setAsking(true);
    setError("");
    try {
      const result = await api.askAnalyst(trimmed);
      setTurns((current) => [
        ...current,
        {
          id: nextId.current++,
          question: trimmed,
          answer: result.answer,
          metrics: result.metrics,
        },
      ]);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The analyst could not answer that.");
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
      <Link
        to="/admin"
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition hover:text-white"
      >
        <ChevronLeft className="h-4 w-4" aria-hidden />
        Back to admin console
      </Link>

      <div className="mt-4 flex items-center gap-2.5">
        <h1 className="text-3xl font-extrabold tracking-tight text-white">Insights</h1>
        <Badge tone="volt">
          <ShieldCheck className="mr-1 h-3 w-3" aria-hidden />
          Admin only
        </Badge>
      </div>
      <p className="mt-1.5 max-w-2xl text-slate-400">
        Two agents over your live gym data. Both read from vetted queries only, so every number
        here comes from the database rather than from the model.
      </p>

      <div className="mt-7 flex gap-2 border-b border-ink-800">
        {(
          [
            { id: "analyst", label: "Data analyst", icon: BarChart3 },
            { id: "advisor", label: "Advisor", icon: Compass },
          ] as const
        ).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition ${
              tab === id
                ? "border-volt-400 text-volt-400"
                : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            <Icon className="h-4 w-4" aria-hidden />
            {label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        <Alert kind="error" message={error} />
      </div>

      {tab === "analyst" ? (
        <section className="mt-6">
          {turns.length === 0 && !asking && (
            <div className="card p-6">
              <div className="flex items-center gap-2.5">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-volt-400/10 text-volt-400">
                  <BarChart3 className="h-5 w-5" aria-hidden />
                </span>
                <div>
                  <p className="font-bold text-white">Ask about your gym</p>
                  <p className="text-sm text-slate-400">
                    Revenue, renewals, attendance, trainer load, churn risk.
                  </p>
                </div>
              </div>

              {metrics && metrics.length > 0 && (
                <p className="mt-4 text-xs leading-relaxed text-slate-500">
                  Reading from {metrics.length} vetted metrics. The analyst cannot query anything
                  else, and cannot see passwords or member chat transcripts.
                </p>
              )}

              <div className="mt-5 flex flex-wrap gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => void ask(suggestion)}
                    className="rounded-full border border-ink-700 px-3.5 py-2 text-xs text-slate-300 transition hover:border-volt-500/50 hover:text-white"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-6">
            {turns.map((turn) => (
              <div key={turn.id} className="space-y-3">
                <div className="flex justify-end">
                  <p className="max-w-[80%] rounded-2xl bg-volt-400 px-4 py-2.5 text-sm font-medium text-ink-950">
                    {turn.question}
                  </p>
                </div>

                <div className="card p-5">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                    {turn.answer}
                  </p>

                  {turn.metrics.length > 0 && (
                    <div className="mt-5 space-y-3">
                      <p className="text-xs uppercase tracking-wider text-slate-500">
                        Data it read
                      </p>
                      {turn.metrics.map((metric) => (
                        <MetricGrid key={metric.key} metric={metric} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {asking && <Spinner label="Querying your data" />}
            <div ref={endRef} />
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              void ask(draft);
            }}
            className="sticky bottom-4 mt-6 flex items-center gap-2 rounded-2xl border border-ink-700 bg-ink-900/95 p-2.5 backdrop-blur"
          >
            <input
              className="input flex-1 border-0 bg-transparent focus:ring-0"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask the analyst a question about your gym…"
              maxLength={500}
              aria-label="Question for the data analyst"
            />
            <Button type="submit" disabled={!draft.trim() || asking} aria-label="Ask" className="px-3">
              <ArrowUp className="h-4 w-4" aria-hidden />
            </Button>
          </form>
        </section>
      ) : (
        <section className="mt-6">
          {loadingReport && !report ? (
            <Spinner label="Reviewing your gym" />
          ) : report ? (
            <>
              <div className="card p-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-center gap-2.5">
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-volt-400/10 text-volt-400">
                      <Lightbulb className="h-5 w-5" aria-hidden />
                    </span>
                    <div>
                      <p className="font-bold text-white">Owner's briefing</p>
                      <p className="text-sm text-slate-400">{report.summary}</p>
                    </div>
                  </div>
                  <Button variant="outline" busy={loadingReport} onClick={() => void loadReport()}>
                    <RefreshCw className="h-4 w-4" aria-hidden />
                    Refresh
                  </Button>
                </div>

                <p className="mt-5 whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                  {report.briefing}
                </p>
              </div>

              {report.recommendations.length > 0 && (
                <div className="mt-8">
                  <SectionTitle
                    title="Recommendations"
                    subtitle="Highest priority first. Each one names the evidence behind it."
                  />
                  <div className="grid gap-4 md:grid-cols-2">
                    {report.recommendations.map((item) => (
                      <RecommendationCard key={item.title} item={item} />
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </section>
      )}
    </div>
  );
}
