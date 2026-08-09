import { useCallback, useEffect, useState } from "react";
import { CalendarPlus, ClipboardList, Trash2, Users } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import type { GymClass, Person, Programme } from "../lib/api";
import { classTime, longDate } from "../lib/format";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  Field,
  SectionTitle,
  Spinner,
  Stat,
} from "../components/ui";

const DISCIPLINES = ["gym", "yoga", "mma"];

export default function TrainerDashboard() {
  const { user } = useAuth();

  const [members, setMembers] = useState<Person[] | null>(null);
  const [classes, setClasses] = useState<GymClass[]>([]);
  const [selected, setSelected] = useState<Person | null>(null);
  const [programmes, setProgrammes] = useState<Programme[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [kind, setKind] = useState<"workout" | "diet">("workout");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [savingProgramme, setSavingProgramme] = useState(false);

  const [className, setClassName] = useState("");
  const [discipline, setDiscipline] = useState("gym");
  const [startsAt, setStartsAt] = useState("");
  const [capacity, setCapacity] = useState(15);
  const [savingClass, setSavingClass] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextMembers, nextClasses] = await Promise.all([api.myMembers(), api.classes()]);
      setMembers(nextMembers);
      setClasses(nextClasses);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load your roster.");
      setMembers([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openMember = async (member: Person) => {
    setSelected(member);
    setError("");
    setNotice("");
    setTitle("");
    setContent("");
    try {
      setProgrammes(await api.memberProgrammes(member.id));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load their programmes.");
      setProgrammes([]);
    }
  };

  const assignProgramme = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    setSavingProgramme(true);
    setError("");
    setNotice("");
    try {
      await api.createProgramme({ member_id: selected.id, kind, title, content });
      setNotice(`${kind === "diet" ? "Diet" : "Workout"} plan sent to ${selected.full_name}.`);
      setTitle("");
      setContent("");
      setProgrammes(await api.memberProgrammes(selected.id));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save that programme.");
    } finally {
      setSavingProgramme(false);
    }
  };

  const addClass = async (event: React.FormEvent) => {
    event.preventDefault();
    setSavingClass(true);
    setError("");
    setNotice("");
    try {
      await api.createClass({
        name: className,
        discipline,
        instructor: user?.full_name ?? "Coach",
        starts_at: new Date(startsAt).toISOString().slice(0, 19),
        capacity,
      });
      setNotice("Class added to the timetable.");
      setClassName("");
      setStartsAt("");
      setClasses(await api.classes());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not add that class.");
    } finally {
      setSavingClass(false);
    }
  };

  const removeClass = async (session: GymClass) => {
    setError("");
    setNotice("");
    try {
      await api.deleteClass(session.id);
      setNotice(`${session.name} removed.`);
      setClasses(await api.classes());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not remove that class.");
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <h1 className="text-3xl font-extrabold tracking-tight text-white">Trainer desk</h1>
      <p className="mt-1.5 text-slate-400">Your members, their programmes, and your timetable.</p>

      <div className="mt-6 space-y-3">
        <Alert kind="error" message={error} />
        <Alert kind="success" message={notice} />
      </div>

      <div className="mt-8 grid gap-5 sm:grid-cols-3">
        <Stat label="My members" value={members?.length ?? "—"} icon={<Users className="h-4 w-4" />} />
        <Stat
          label="Upcoming classes"
          value={classes.length}
          icon={<CalendarPlus className="h-4 w-4" />}
        />
        <Stat
          label="Seats booked"
          value={classes.reduce((total, session) => total + session.seats_taken, 0)}
          icon={<ClipboardList className="h-4 w-4" />}
        />
      </div>

      <div className="mt-12 grid gap-10 lg:grid-cols-[20rem_1fr]">
        <section>
          <SectionTitle title="My members" />
          {!members ? (
            <Spinner label="Loading members" />
          ) : members.length === 0 ? (
            <EmptyState
              icon={<Users className="h-8 w-8" />}
              title="No members assigned"
              body="An admin needs to assign members to you before you can write their programmes."
            />
          ) : (
            <div className="space-y-2">
              {members.map((member) => (
                <button
                  key={member.id}
                  onClick={() => void openMember(member)}
                  className={`w-full rounded-xl border p-4 text-left transition ${
                    selected?.id === member.id
                      ? "border-volt-500/50 bg-volt-500/5"
                      : "border-ink-700 bg-ink-850 hover:border-ink-600"
                  }`}
                >
                  <p className="font-semibold text-white">{member.full_name}</p>
                  <p className="mt-0.5 truncate text-xs text-slate-400">{member.email}</p>
                  <p className="mt-1.5 text-xs text-slate-500">
                    {member.plan_name ? `${member.plan_name} · ${longDate(member.expires_on)}` : "No package"}
                  </p>
                </button>
              ))}
            </div>
          )}
        </section>

        <section>
          {selected ? (
            <>
              <SectionTitle
                title={`Programme for ${selected.full_name}`}
                subtitle="This appears on their dashboard immediately and FitBot can explain it."
              />

              <form onSubmit={assignProgramme} className="card space-y-4 p-6">
                <div className="grid gap-4 sm:grid-cols-[10rem_1fr]">
                  <Field label="Type">
                    <select
                      className="input"
                      value={kind}
                      onChange={(event) => setKind(event.target.value as "workout" | "diet")}
                    >
                      <option value="workout">Workout</option>
                      <option value="diet">Diet</option>
                    </select>
                  </Field>
                  <Field label="Title">
                    <input
                      className="input"
                      value={title}
                      onChange={(event) => setTitle(event.target.value)}
                      placeholder="e.g. Weeks 1-4: full body strength"
                      required
                      minLength={2}
                    />
                  </Field>
                </div>

                <Field label="Details">
                  <textarea
                    className="input min-h-40 resize-y"
                    value={content}
                    onChange={(event) => setContent(event.target.value)}
                    placeholder={
                      "Day 1 — Squat 3x8 @ 60%\nDay 2 — Rest or 20 min walk\n..."
                    }
                    required
                    minLength={2}
                  />
                </Field>

                <Button type="submit" busy={savingProgramme}>
                  Assign programme
                </Button>
              </form>

              <div className="mt-8">
                <SectionTitle title="Previously assigned" />
                {programmes.length === 0 ? (
                  <p className="text-sm text-slate-500">Nothing assigned to them yet.</p>
                ) : (
                  <div className="space-y-3">
                    {programmes.map((programme) => (
                      <div key={programme.id} className="card p-4">
                        <div className="flex items-center gap-2.5">
                          <h4 className="font-semibold text-white">{programme.title}</h4>
                          <Badge>{programme.kind}</Badge>
                          <span className="ml-auto text-xs text-slate-500">
                            {longDate(programme.created_at)}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm text-slate-400">
                          {programme.content}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <EmptyState
              icon={<ClipboardList className="h-8 w-8" />}
              title="Pick a member"
              body="Select someone from your roster to write or review their workout and diet programme."
            />
          )}
        </section>
      </div>

      <section className="mt-14">
        <SectionTitle title="Timetable" subtitle="Add a class and members can book it right away." />

        <form onSubmit={addClass} className="card grid gap-4 p-6 sm:grid-cols-4">
          <Field label="Class name">
            <input
              className="input"
              value={className}
              onChange={(event) => setClassName(event.target.value)}
              placeholder="Morning Strength"
              required
              minLength={2}
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
          <Field label="Starts at">
            <input
              className="input"
              type="datetime-local"
              value={startsAt}
              onChange={(event) => setStartsAt(event.target.value)}
              required
            />
          </Field>
          <Field label="Capacity">
            <input
              className="input"
              type="number"
              min={1}
              max={200}
              value={capacity}
              onChange={(event) => setCapacity(Number(event.target.value))}
              required
            />
          </Field>
          <div className="sm:col-span-4">
            <Button type="submit" busy={savingClass}>
              <CalendarPlus className="h-4 w-4" aria-hidden />
              Add class
            </Button>
          </div>
        </form>

        {classes.length > 0 && (
          <div className="mt-5 space-y-3">
            {classes.map((session) => (
              <div key={session.id} className="card flex items-center justify-between gap-4 p-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className="truncate font-semibold text-white">{session.name}</h4>
                    <Badge>{session.discipline}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-400">
                    {classTime(session.starts_at)} · {session.seats_taken}/{session.capacity} booked
                  </p>
                </div>
                <Button
                  variant="danger"
                  aria-label={`Remove ${session.name}`}
                  onClick={() => void removeClass(session)}
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
