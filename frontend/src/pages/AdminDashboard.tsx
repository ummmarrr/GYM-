import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  CalendarCheck,
  ClipboardCheck,
  IndianRupee,
  Megaphone,
  RotateCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  UserPlus,
  Users,
} from "lucide-react";

import { api, ApiError } from "../lib/api";
import type { FrontDeskNotice, KnowledgeDoc, Overview, Person, Role } from "../lib/api";
import { longDate, rupees } from "../lib/format";
import { Alert, Badge, Button, Field, SectionTitle, Spinner, Stat } from "../components/ui";

const DISCIPLINES = ["gym", "yoga", "mma", "reception"];

export default function AdminDashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDoc[]>([]);
  const [notices, setNotices] = useState<FrontDeskNotice[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [newRole, setNewRole] = useState<"member" | "trainer" | "reception">("member");
  const [creating, setCreating] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [discipline, setDiscipline] = useState("gym");
  const [uploading, setUploading] = useState(false);
  const [noticeKind, setNoticeKind] = useState<FrontDeskNotice["kind"]>("info");
  const [noticeTitle, setNoticeTitle] = useState("");
  const [noticeBody, setNoticeBody] = useState("");
  const [savingNotice, setSavingNotice] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextOverview, nextPeople, nextDocs, nextNotices] = await Promise.all([
        api.overview(),
        api.people(),
        api.documents(),
        api.frontDeskNotices(),
      ]);
      setOverview(nextOverview);
      setPeople(nextPeople);
      setDocuments(nextDocs);
      setNotices(nextNotices);
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

  const createNotice = async (event: React.FormEvent) => {
    event.preventDefault();
    setSavingNotice(true);
    await run(async () => {
      await api.createNotice({
        kind: noticeKind,
        title: noticeTitle,
        message: noticeBody,
        active_from: new Date().toISOString().slice(0, 19),
        active_until: null,
      });
      setNoticeTitle("");
      setNoticeBody("");
      return "Front desk notice published.";
    });
    setSavingNotice(false);
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
        to="/front-desk"
        className="card mt-6 flex flex-wrap items-center justify-between gap-4 border-volt-500/30 p-5 transition hover:border-volt-400"
      >
        <span className="flex items-center gap-3.5">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-volt-400/10 text-volt-400">
            <ClipboardCheck className="h-5 w-5" aria-hidden />
          </span>
          <span>
            <span className="block font-bold text-white">Front desk check-in</span>
            <span className="block text-sm text-slate-400">
              Scan gym passes, review member details and record attendance.
            </span>
          </span>
        </span>
        <span className="inline-flex items-center gap-2 rounded-xl bg-volt-400 px-4 py-2.5 text-sm font-semibold text-ink-950">
          Open front desk
          <ArrowRight className="h-4 w-4" aria-hidden />
        </span>
      </Link>

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
          title="Add an account"
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
              onChange={(event) =>
                setNewRole(event.target.value as "member" | "trainer" | "reception")
              }
            >
              <option value="member">Member</option>
              <option value="trainer">Trainer</option>
              <option value="reception">Reception</option>
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
                <th className="px-5 py-3.5 font-medium">Pass</th>
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
                      <option value="reception">reception</option>
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
                  <td className="px-5 py-4">
                    {person.role === "member" ? (
                      <div className="flex flex-col items-start gap-1.5">
                        <Button
                          variant="ghost"
                          aria-label={`Rotate gym pass for ${person.full_name}`}
                          onClick={() =>
                            void run(async () => {
                              await api.rotateMemberPass(person.id);
                              return `${person.full_name}'s old pass has been revoked and replaced.`;
                            })
                          }
                        >
                          <RotateCw className="h-4 w-4" aria-hidden />
                          Rotate
                        </Button>
                        <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-slate-300 hover:bg-ink-700 hover:text-white">
                          <Upload className="h-3.5 w-3.5" aria-hidden />
                          Enroll photo
                          <input
                            className="sr-only"
                            type="file"
                            accept="image/jpeg,image/png"
                            onChange={(event) => {
                              const photo = event.target.files?.[0];
                              event.target.value = "";
                              if (!photo) return;
                              void run(async () => {
                                await api.uploadMemberPhoto(person.id, photo);
                                return `${person.full_name}'s check-in photo was updated.`;
                              });
                            }}
                          />
                        </label>
                      </div>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-14">
        <SectionTitle
          title="Front desk notices"
          subtitle="Active notices appear in member briefings during check-in."
        />
        <form onSubmit={createNotice} className="card grid gap-4 p-6 sm:grid-cols-4">
          <Field label="Type">
            <select
              className="input"
              value={noticeKind}
              onChange={(event) =>
                setNoticeKind(event.target.value as FrontDeskNotice["kind"])
              }
            >
              <option value="info">Information</option>
              <option value="repair">Machine repair</option>
              <option value="closure">Closure</option>
            </select>
          </Field>
          <Field label="Title">
            <input
              className="input"
              value={noticeTitle}
              onChange={(event) => setNoticeTitle(event.target.value)}
              required
              maxLength={120}
            />
          </Field>
          <Field label="Message">
            <input
              className="input"
              value={noticeBody}
              onChange={(event) => setNoticeBody(event.target.value)}
              required
              maxLength={500}
            />
          </Field>
          <div className="flex items-end">
            <Button type="submit" busy={savingNotice}>
              <Megaphone className="h-4 w-4" aria-hidden />
              Publish
            </Button>
          </div>
        </form>

        {notices.length > 0 && (
          <div className="mt-5 space-y-3">
            {notices.map((item) => (
              <div key={item.id} className="card flex flex-wrap items-center justify-between gap-4 p-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-white">{item.title}</p>
                    <Badge
                      tone={
                        !item.active_until || new Date(item.active_until) >= new Date()
                          ? "volt"
                          : "neutral"
                      }
                    >
                      {!item.active_until || new Date(item.active_until) >= new Date()
                        ? "active"
                        : "paused"}
                    </Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-400">{item.message}</p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() =>
                      void run(async () => {
                        const active =
                          !item.active_until || new Date(item.active_until) >= new Date();
                        await api.updateNotice(item.id, {
                          kind: item.kind,
                          title: item.title,
                          message: item.message,
                          active_from: active
                            ? item.active_from
                            : new Date().toISOString().slice(0, 19),
                          active_until: active
                            ? new Date().toISOString().slice(0, 19)
                            : null,
                        });
                        return `${item.title} ${active ? "paused" : "activated"}.`;
                      })
                    }
                  >
                    {!item.active_until || new Date(item.active_until) >= new Date()
                      ? "Pause"
                      : "Activate"}
                  </Button>
                  <Button
                    variant="danger"
                    aria-label={`Delete notice ${item.title}`}
                    onClick={() =>
                      void run(async () => {
                        await api.deleteNotice(item.id);
                        return `${item.title} deleted.`;
                      })
                    }
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
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
