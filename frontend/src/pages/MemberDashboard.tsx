import { useCallback, useEffect, useState } from "react";
import {
  CalendarDays,
  ClipboardList,
  CreditCard,
  Dumbbell,
  Salad,
  Target,
} from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import type { GymClass, Profile, Programme } from "../lib/api";
import { classTime, longDate, quotaLabel } from "../lib/format";
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  EmptyState,
  Field,
  SectionTitle,
  Spinner,
} from "../components/ui";

const EXPERIENCE = ["beginner", "intermediate", "advanced"];

export default function MemberDashboard() {
  const { user, entitlements, refresh } = useAuth();

  const [classes, setClasses] = useState<GymClass[] | null>(null);
  const [programmes, setProgrammes] = useState<Programme[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextClasses, nextProgrammes, nextProfile] = await Promise.all([
        api.classes(),
        api.myProgrammes(),
        api.profile(),
      ]);
      setClasses(nextClasses);
      setProgrammes(nextProgrammes);
      setProfile(nextProfile);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load your dashboard.");
      setClasses([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleBooking = async (session: GymClass) => {
    setBusyId(session.id);
    setError("");
    setNotice("");
    try {
      const result = session.booked_by_me
        ? await api.cancelBooking(session.id)
        : await api.bookClass(session.id);
      setNotice(result.message);
      setClasses(await api.classes());
      await refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not update that booking.");
    } finally {
      setBusyId(null);
    }
  };

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!profile) return;
    setSavingProfile(true);
    setError("");
    setNotice("");
    try {
      setProfile(
        await api.saveProfile({
          goal: profile.goal,
          experience_level: profile.experience_level,
          injuries_or_limits: profile.injuries_or_limits,
          equipment_access: profile.equipment_access,
        }),
      );
      setNotice("Saved. FitBot will use this from your next message.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save your profile.");
    } finally {
      setSavingProfile(false);
    }
  };

  const expiringSoon =
    entitlements?.days_remaining !== null &&
    entitlements?.days_remaining !== undefined &&
    entitlements.days_remaining <= 7;

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <h1 className="text-3xl font-extrabold tracking-tight text-white">
        Hi {user?.full_name.split(" ")[0]}
      </h1>
      <p className="mt-1.5 text-slate-400">Here is where your training stands today.</p>

      <div className="mt-6 space-y-3">
        <Alert kind="error" message={error} />
        <Alert kind="success" message={notice} />
      </div>

      <section className="mt-8">
        <div className="card p-6">
          {entitlements?.has_active_membership ? (
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div>
                <div className="flex items-center gap-2.5">
                  <h2 className="text-xl font-bold text-white">{entitlements.plan_name}</h2>
                  <Badge tone={expiringSoon ? "warn" : "volt"}>
                    {expiringSoon ? "Expiring soon" : "Active"}
                  </Badge>
                </div>
                <p className="mt-1.5 text-sm text-slate-400">
                  Valid until {longDate(entitlements.expires_on)} · {entitlements.days_remaining}{" "}
                  days left
                </p>
                <dl className="mt-5 grid grid-cols-2 gap-5 sm:grid-cols-3">
                  <div>
                    <dt className="text-xs uppercase tracking-wider text-slate-500">Access</dt>
                    <dd className="mt-1 text-sm font-medium text-slate-200">
                      {entitlements.allowed_disciplines.join(", ").toUpperCase()}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wider text-slate-500">Classes</dt>
                    <dd className="mt-1 text-sm font-medium text-slate-200">
                      {entitlements.classes_booked_this_month} used ·{" "}
                      {quotaLabel(entitlements.monthly_class_quota)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wider text-slate-500">Programme</dt>
                    <dd className="mt-1 text-sm font-medium text-slate-200">
                      {entitlements.personalised_programme ? "Trainer-written" : "Not included"}
                    </dd>
                  </div>
                </dl>
              </div>
              <ButtonLink to="/packages" variant="outline">
                <CreditCard className="h-4 w-4" aria-hidden />
                Change package
              </ButtonLink>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-5">
              <div>
                <h2 className="text-lg font-bold text-white">No active package</h2>
                <p className="mt-1 text-sm text-slate-400">
                  Pick a package to unlock classes and a trainer-written programme.
                </p>
              </div>
              <ButtonLink to="/packages">See packages</ButtonLink>
            </div>
          )}
        </div>
      </section>

      <div className="mt-10 grid gap-10 lg:grid-cols-2">
        <section>
          <SectionTitle title="My programmes" subtitle="Written by your assigned trainer." />
          {programmes.length === 0 ? (
            <EmptyState
              icon={<ClipboardList className="h-8 w-8" />}
              title="No programme yet"
              body="Once a trainer is assigned to you, your workout and diet plans appear here. Ask FitBot for general guidance meanwhile."
            />
          ) : (
            <div className="space-y-4">
              {programmes.map((programme) => (
                <article key={programme.id} className="card p-5">
                  <div className="flex items-center gap-2.5">
                    <span className="text-volt-400">
                      {programme.kind === "diet" ? (
                        <Salad className="h-4 w-4" aria-hidden />
                      ) : (
                        <Dumbbell className="h-4 w-4" aria-hidden />
                      )}
                    </span>
                    <h3 className="font-bold text-white">{programme.title}</h3>
                    <Badge>{programme.kind}</Badge>
                  </div>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
                    {programme.content}
                  </p>
                  <p className="mt-3 text-xs text-slate-500">
                    Assigned {longDate(programme.created_at)}
                  </p>
                </article>
              ))}
            </div>
          )}
        </section>

        <section>
          <SectionTitle title="Upcoming classes" subtitle="Your package decides what you can book." />
          {!classes ? (
            <Spinner label="Loading classes" />
          ) : classes.length === 0 ? (
            <EmptyState
              icon={<CalendarDays className="h-8 w-8" />}
              title="Nothing scheduled"
              body="No upcoming classes on the timetable right now. Check back soon."
            />
          ) : (
            <div className="space-y-3">
              {classes.map((session) => (
                <div key={session.id} className="card flex items-center justify-between gap-4 p-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="truncate font-semibold text-white">{session.name}</h3>
                      <Badge>{session.discipline}</Badge>
                    </div>
                    <p className="mt-1 truncate text-sm text-slate-400">
                      {classTime(session.starts_at)} · {session.instructor}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {session.seats_left} of {session.capacity} seats left
                    </p>
                  </div>
                  <Button
                    variant={session.booked_by_me ? "danger" : "outline"}
                    busy={busyId === session.id}
                    disabled={!session.booked_by_me && session.seats_left === 0}
                    onClick={() => void toggleBooking(session)}
                  >
                    {session.booked_by_me
                      ? "Cancel"
                      : session.seats_left === 0
                        ? "Full"
                        : "Book"}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="mt-12">
        <SectionTitle
          title="My fitness profile"
          subtitle="FitBot reads this before every answer, so keep it honest."
        />
        {profile && (
          <form onSubmit={saveProfile} className="card grid gap-5 p-6 sm:grid-cols-2">
            <Field label="Main goal">
              <input
                className="input"
                placeholder="e.g. lose 6 kg and get stronger"
                value={profile.goal ?? ""}
                onChange={(event) => setProfile({ ...profile, goal: event.target.value })}
              />
            </Field>

            <Field label="Experience level">
              <select
                className="input"
                value={profile.experience_level ?? ""}
                onChange={(event) =>
                  setProfile({ ...profile, experience_level: event.target.value })
                }
              >
                <option value="">Not set</option>
                {EXPERIENCE.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Equipment access">
              <input
                className="input"
                placeholder="e.g. full gym, or dumbbells at home"
                value={profile.equipment_access ?? ""}
                onChange={(event) =>
                  setProfile({ ...profile, equipment_access: event.target.value })
                }
              />
            </Field>

            <Field
              label="Injuries or limits"
              hint="FitBot will work around these and escalate anything medical to a trainer."
            >
              <input
                className="input"
                placeholder="e.g. left knee pain on deep squats"
                value={profile.injuries_or_limits ?? ""}
                onChange={(event) =>
                  setProfile({ ...profile, injuries_or_limits: event.target.value })
                }
              />
            </Field>

            <div className="sm:col-span-2">
              <Button type="submit" busy={savingProfile}>
                <Target className="h-4 w-4" aria-hidden />
                Save profile
              </Button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
