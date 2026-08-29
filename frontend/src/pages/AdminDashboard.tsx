import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  CalendarCheck,
  IndianRupee,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  UserPlus,
  Users,
} from "lucide-react";

import { api, ApiError } from "../lib/api";
import type { KnowledgeDoc, Overview, Person, Role } from "../lib/api";
import { longDate, rupees } from "../lib/format";
import { Alert, Badge, Button, Field, SectionTitle, Spinner, Stat } from "../components/ui";

const DISCIPLINES = ["gym", "yoga", "mma", "reception"];

export default function AdminDashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDoc[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [newRole, setNewRole] = useState<"member" | "trainer">("member");
  const [creating, setCreating] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [discipline, setDiscipline] = useState("gym");
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextOverview, nextPeople, nextDocs] = await Promise.all([
        api.overview(),
        api.people(),
        api.documents(),
      ]);
      setOverview(nextOverview);
      setPeople(nextPeople);
      setDocuments(nextDocs);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load the admin data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (action: () => Promise<string>) => {
    setError("");
    setNotice("");
    try {
      setNotice(await action());
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "That action did not go through.");
    }
  };

  const createPerson = async (event: React.FormEvent) => {
    event.preventDefault();
    setCreating(true);
    await run(async () => {
      await api.createPerson({ email, full_name: fullName, password, role: newRole });
      setEmail("");
      setFullName("");
      setPassword("");
      return `${fullName} added as ${newRole}.`;
    });
    setCreating(false);
  };

  const upload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    await run(async () => {
      const document = await api.uploadDocument(file, discipline);
      setFile(null);
      return `${document.filename} ingested into ${document.discipline} (${document.chunk_count} chunks${
        document.ingest_mode ? `, ${document.ingest_mode}` : ""
      }).`;
    });
    setUploading(false);
  };

  const trainers = people.filter((person) => person.role === "trainer");

  if (loading) return <Spinner label="Loading admin data" />;

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <div className="flex items-center gap-2.5">
        <h1 className="text-3xl font-extrabold tracking-tight text-white">Admin console</h1>
        <Badge tone="volt">
          <ShieldCheck className="mr-1 h-3 w-3" aria-hidden />
          Web app only
        </Badge>
      </div>
      <p className="mt-1.5 text-slate-400">
        Accounts, packages, the timetable and everything FitBot is allowed to quote.
      </p>

      <Link
        to="/admin/insights"
        className="card mt-6 flex flex-wrap items-center justify-between gap-4 p-5 transition hover:border-volt-500/40"
      >
        <span className="flex items-center gap-3.5">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-volt-400/10 text-volt-400">
            <Sparkles className="h-5 w-5" aria-hidden />
          </span>
          <span>
            <span className="block font-bold text-white">Insights</span>
            <span className="block text-sm text-slate-400">
              Ask the data analyst about your gym, or get recommendations on what to fix next.
            </span>
          </span>
        </span>
        <span className="inline-flex items-center gap-2 rounded-xl border border-ink-600 px-4 py-2.5 text-sm font-semibold text-slate-200">
          Open
          <ArrowRight className="h-4 w-4" aria-hidden />
        </span>
      </Link>

      <div className="mt-6 space-y-3">
        <Alert kind="error" message={error} />
        <Alert kind="success" message={notice} />
      </div>

      {overview && (
        <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Members" value={overview.members} icon={<Users className="h-4 w-4" />} />
          <Stat
            label="Active packages"
            value={overview.active_memberships}
            icon={<CalendarCheck className="h-4 w-4" />}
          />
          <Stat
            label="Revenue"
            value={rupees(overview.revenue_paise)}
            icon={<IndianRupee className="h-4 w-4" />}
          />
          <Stat
            label="Knowledge docs"
            value={documents.length}
            icon={<BookOpen className="h-4 w-4" />}
          />
        </div>
      )}

      <section className="mt-14">
        <SectionTitle
          title="Add a member or trainer"
          subtitle="Admin accounts are created only from the server seed script, never from the browser."
        />
        <form onSubmit={createPerson} className="card grid gap-4 p-6 sm:grid-cols-4">
          <Field label="Full name">
            <input
              className="input"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
              minLength={2}
            />
          </Field>
          <Field label="Email">
            <input
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </Field>
          <Field label="Temporary password">
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
            />
          </Field>
          <Field label="Role">
            <select
              className="input"
              value={newRole}
              onChange={(event) => setNewRole(event.target.value as "member" | "trainer")}
            >
              <option value="member">Member</option>
              <option value="trainer">Trainer</option>
            </select>
          </Field>
          <div className="sm:col-span-4">
            <Button type="submit" busy={creating}>
              <UserPlus className="h-4 w-4" aria-hidden />
              Create account
            </Button>
          </div>
        </form>
      </section>

      <section className="mt-14">
        <SectionTitle title="All accounts" subtitle={`${people.length} in total.`} />
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-ink-700 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-5 py-3.5 font-medium">Name</th>
                <th className="px-5 py-3.5 font-medium">Role</th>
                <th className="px-5 py-3.5 font-medium">Package</th>
                <th className="px-5 py-3.5 font-medium">Trainer</th>
                <th className="px-5 py-3.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {people.map((person) => (
                <tr key={person.id} className="hover:bg-ink-800/40">
                  <td className="px-5 py-4">
                    <p className="font-medium text-white">{person.full_name}</p>
                    <p className="text-xs text-slate-500">{person.email}</p>
                  </td>
                  <td className="px-5 py-4">
                    <select
                      className="rounded-lg border border-ink-700 bg-ink-900 px-2.5 py-1.5 text-xs text-slate-200"
                      value={person.role}
                      onChange={(event) => {
                        // Read the value now: this select is controlled, so React resets the
                        // DOM node back to the old role before the async callback resumes.
                        const role = event.target.value as Role;
                        void run(async () => {
                          await api.changeRole(person.id, role);
                          return `${person.full_name} is now a ${role}.`;
                        });
                      }}
                    >
                      <option value="member">member</option>
                      <option value="trainer">trainer</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="px-5 py-4 text-slate-300">
                    {person.plan_name ? (
                      <>
                        {person.plan_name}
                        <span className="block text-xs text-slate-500">
                          until {longDate(person.expires_on)}
                        </span>
                      </>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    {person.role === "member" ? (
                      <select
                        className="rounded-lg border border-ink-700 bg-ink-900 px-2.5 py-1.5 text-xs text-slate-200"
                        defaultValue=""
                        onChange={(event) => {
                          const trainerId = event.target.value;
                          if (!trainerId) return;
                          void run(async () => {
                            await api.assignTrainer(person.id, trainerId);
                            return `Trainer assigned to ${person.full_name}.`;
                          });
                        }}
                      >
                        <option value="">Assign…</option>
                        {trainers.map((trainer) => (
                          <option key={trainer.id} value={trainer.id}>
                            {trainer.full_name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    <button
                      onClick={() =>
                        void run(async () => {
                          await api.updatePerson(person.id, { active: !person.active });
                          return `${person.full_name} ${person.active ? "deactivated" : "reactivated"}.`;
                        })
                      }
                    >
                      <Badge tone={person.active ? "volt" : "danger"}>
                        {person.active ? "active" : "inactive"}
                      </Badge>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-14">
        <SectionTitle
          title="FitBot knowledge base"
          subtitle="FitBot may only quote these documents. Nothing else reaches a member."
        />

        <form onSubmit={upload} className="card grid gap-4 p-6 sm:grid-cols-3">
          <Field label="PDF file" hint="Up to 20 MB.">
            <input
              className="input file:mr-3 file:rounded-lg file:border-0 file:bg-ink-700 file:px-3 file:py-1 file:text-slate-200"
              type="file"
              accept="application/pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              required
            />
          </Field>
          <Field label="Discipline">
            <select
              className="input"
              value={discipline}
              onChange={(event) => setDiscipline(event.target.value)}
            >
              {DISCIPLINES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>
          <div className="flex items-end">
            <Button type="submit" busy={uploading} disabled={!file}>
              <Upload className="h-4 w-4" aria-hidden />
              Ingest PDF
            </Button>
          </div>
        </form>

        {documents.length > 0 && (
          <div className="mt-5 space-y-3">
            {documents.map((document) => (
              <div key={document.id} className="card flex items-center justify-between gap-4 p-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="truncate font-medium text-white">{document.filename}</p>
                    <Badge>{document.discipline}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {document.chunk_count} chunks
                    {document.ingest_mode ? ` · ${document.ingest_mode}` : ""} · added{" "}
                    {longDate(document.created_at)}
                  </p>
                </div>
                <Button
                  variant="danger"
                  aria-label={`Remove ${document.filename}`}
                  onClick={() =>
                    void run(async () => {
                      const result = await api.deleteDocument(document.id);
                      return result.message;
                    })
                  }
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </Button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
