import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserQRCodeReader, type IScannerControls } from "@zxing/browser";
import {
  CalendarDays,
  Camera,
  CheckCircle2,
  Clock3,
  Search,
  ShieldAlert,
  UserRound,
  XCircle,
} from "lucide-react";

import { Alert, Badge, Button, EmptyState, Field, Spinner } from "../components/ui";
import { api, ApiError } from "../lib/api";
import type { FrontDeskBriefing, FrontDeskMember } from "../lib/api";
import { classTime, longDate, quotaLabel } from "../lib/format";

type MatchMethod = "qr" | "manual";

export default function FrontDesk() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const controlsRef = useRef<IScannerControls | null>(null);
  const lookupInFlight = useRef(false);
  const lastToken = useRef<string | null>(null);

  const [scanning, setScanning] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [briefing, setBriefing] = useState<FrontDeskBriefing | null>(null);
  const [method, setMethod] = useState<MatchMethod>("qr");
  const [checkingIn, setCheckingIn] = useState(false);
  const [lookupBusy, setLookupBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FrontDeskMember[]>([]);
  const [searching, setSearching] = useState(false);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);

  const stopCamera = useCallback(() => {
    controlsRef.current?.stop();
    controlsRef.current = null;
    setScanning(false);
  }, []);

  const lookupToken = useCallback(
    async (token: string) => {
      const normalized = token.trim();
      if (!normalized || lookupInFlight.current || normalized === lastToken.current) return;

      lookupInFlight.current = true;
      lastToken.current = normalized;
      setLookupBusy(true);
      setError("");
      setSuccess("");
      stopCamera();
      try {
        setBriefing(await api.frontDeskLookup(normalized));
        setMethod("qr");
      } catch (caught) {
        lastToken.current = null;
        setError(caught instanceof ApiError ? caught.message : "That pass could not be read.");
      } finally {
        lookupInFlight.current = false;
        setLookupBusy(false);
      }
    },
    [stopCamera],
  );

  const startCamera = useCallback(async () => {
    stopCamera();
    setCameraError("");
    setError("");
    setSuccess("");
    lastToken.current = null;

    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Camera scanning is not supported by this browser. Use member search instead.");
      return;
    }
    if (!videoRef.current) return;

    try {
      const reader = new BrowserQRCodeReader();
      controlsRef.current = await reader.decodeFromVideoDevice(
        undefined,
        videoRef.current,
        (result) => {
          if (result) void lookupToken(result.getText());
        },
      );
      setScanning(true);
    } catch (caught) {
      const name = caught instanceof DOMException ? caught.name : "";
      setCameraError(
        name === "NotAllowedError" || name === "SecurityError"
          ? "Camera permission was denied. Allow camera access or use member search."
          : "The camera could not be started. Check that it is connected and not in use.",
      );
      setScanning(false);
    }
  }, [lookupToken, stopCamera]);

  useEffect(() => stopCamera, [stopCamera]);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    if (briefing?.member.photo_available) {
      void api
        .memberPhoto(briefing.member.id)
        .then((blob) => {
          if (cancelled) return;
          objectUrl = URL.createObjectURL(blob);
          setPhotoUrl(objectUrl);
        })
        .catch(() => {
          if (!cancelled) setPhotoUrl(null);
        });
    } else {
      setPhotoUrl(null);
    }
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [briefing?.member.id, briefing?.member.photo_available]);

  const restart = useCallback(async () => {
    setBriefing(null);
    setResults([]);
    setQuery("");
    lastToken.current = null;
    await startCamera();
  }, [startCamera]);

  const search = async (event: React.FormEvent) => {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setSearching(true);
    setError("");
    try {
      setResults(await api.frontDeskSearch(query.trim()));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Member search failed.");
    } finally {
      setSearching(false);
    }
  };

  const selectMember = async (person: FrontDeskMember) => {
    stopCamera();
    setLookupBusy(true);
    setError("");
    try {
      setBriefing(await api.frontDeskBriefing(person.id));
      setMethod("manual");
      setResults([]);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load this member.");
    } finally {
      setLookupBusy(false);
    }
  };

  const confirm = async () => {
    if (!briefing) return;
    setCheckingIn(true);
    setError("");
    try {
      const result = await api.frontDeskCheckIn(briefing.member.id, method);
      const message =
        result.already_checked_in
          ? `${briefing.member.full_name} was already checked in recently.`
          : `${briefing.member.full_name} checked in successfully.`;
      setBriefing(null);
      setResults([]);
      lastToken.current = null;
      await startCamera();
      setSuccess(message);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Check-in could not be completed.");
    } finally {
      setCheckingIn(false);
    }
  };

  const entitlements = briefing?.entitlements;
  const remaining =
    entitlements &&
    typeof entitlements.monthly_class_quota === "number" &&
    typeof entitlements.classes_booked_this_month === "number"
      ? entitlements.monthly_class_quota < 0
        ? "Unlimited"
        : `${Math.max(
            0,
            entitlements.monthly_class_quota - entitlements.classes_booked_this_month,
          )} remaining`
      : "Not available";

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-3xl font-extrabold tracking-tight text-white">Front desk</h1>
            <Badge tone="volt">Check-in kiosk</Badge>
          </div>
          <p className="mt-1.5 text-slate-400">Scan a gym pass or find a member manually.</p>
        </div>
        <div className="flex gap-3">
          <Button onClick={() => void startCamera()} disabled={scanning || lookupBusy}>
            <Camera className="h-4 w-4" aria-hidden />
            {scanning ? "Scanning…" : "Start scan"}
          </Button>
          <Button variant="outline" onClick={stopCamera} disabled={!scanning}>
            Stop
          </Button>
        </div>
      </div>

      <div className="mt-6 space-y-3" aria-live="polite">
        <Alert kind="error" message={cameraError || error} />
        <Alert kind="success" message={success} />
      </div>

      <div className="mt-7 grid gap-7 lg:grid-cols-[minmax(0,1.1fr)_minmax(360px,.9fr)]">
        <div className="space-y-7">
          <section className="card overflow-hidden">
            <div className="relative aspect-video bg-black">
              <video
                ref={videoRef}
                className="h-full w-full object-cover"
                muted
                playsInline
                aria-label="Gym pass camera preview"
              />
              {!scanning && (
                <div className="absolute inset-0 grid place-items-center bg-ink-950/85 text-center">
                  <div>
                    <Camera className="mx-auto h-10 w-10 text-slate-600" aria-hidden />
                    <p className="mt-3 text-sm text-slate-400">Select Start scan when ready</p>
                  </div>
                </div>
              )}
              {scanning && (
                <div
                  className="pointer-events-none absolute inset-[12%] rounded-2xl border-2 border-volt-400/80"
                  aria-hidden
                />
              )}
            </div>
            <div className="flex items-center justify-between gap-3 border-t border-white/8 px-5 py-3">
              <span className="text-sm text-slate-400">
                {scanning ? "Hold the QR code inside the frame" : "Camera is stopped"}
              </span>
              <Badge tone={scanning ? "volt" : "neutral"}>{scanning ? "Live" : "Idle"}</Badge>
            </div>
          </section>

          <section className="card p-5">
            <h2 className="font-bold text-white">Manual member search</h2>
            <p className="mt-1 text-sm text-slate-400">Use when a pass or camera is unavailable.</p>
            <form onSubmit={search} className="mt-4 flex gap-3">
              <Field label="Name, email or phone">
                <input
                  className="input"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  minLength={2}
                  placeholder="Start typing…"
                />
              </Field>
              <Button className="mt-[22px]" type="submit" busy={searching} disabled={query.trim().length < 2}>
                <Search className="h-4 w-4" aria-hidden />
                Search
              </Button>
            </form>
            {results.length > 0 && (
              <ul className="mt-4 divide-y divide-ink-700" aria-label="Member search results">
                {results.map((person) => (
                  <li key={person.id}>
                    <button
                      className="flex w-full items-center justify-between gap-4 px-2 py-3 text-left hover:bg-ink-800"
                      onClick={() => void selectMember(person)}
                    >
                      <span>
                        <span className="block font-medium text-white">{person.full_name}</span>
                        <span className="block text-xs text-slate-500">{person.email}</span>
                      </span>
                      <Badge tone={person.active ? "volt" : "danger"}>
                        {person.active ? "active" : "inactive"}
                      </Badge>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <section className="min-h-[520px]" aria-label="Member briefing">
          {lookupBusy ? (
            <div className="card"><Spinner label="Looking up member" /></div>
          ) : !briefing ? (
            <div className="card">
              <EmptyState
                icon={<UserRound className="h-9 w-9" />}
                title="Waiting for a member"
                body="Their identity, package status and today's context will appear here."
              />
            </div>
          ) : (
            <div className="card overflow-hidden">
              <div className="flex gap-4 border-b border-white/8 p-5">
                {photoUrl ? (
                  <img
                    src={photoUrl}
                    alt={`${briefing.member.full_name}'s profile`}
                    className="h-24 w-24 shrink-0 rounded-xl object-cover"
                  />
                ) : (
                  <div className="grid h-24 w-24 shrink-0 place-items-center rounded-xl bg-ink-800 text-slate-500">
                    <UserRound className="h-9 w-9" aria-hidden />
                  </div>
                )}
                <div className="min-w-0">
                  <p className="truncate text-xl font-bold text-white">{briefing.member.full_name}</p>
                  <p className="truncate text-sm text-slate-400">{briefing.member.email}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge tone={briefing.member.active ? "volt" : "danger"}>
                      {briefing.member.active ? "Account active" : "Account inactive"}
                    </Badge>
                    <Badge tone={entitlements?.has_active_membership ? "volt" : "danger"}>
                      {entitlements?.has_active_membership ? "Membership active" : "No membership"}
                    </Badge>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-px bg-white/8">
                <BriefStat label="Package" value={entitlements?.plan_name ?? "None"} />
                <BriefStat label="Expires" value={longDate(entitlements?.expires_on ?? null)} />
                <BriefStat
                  label="Monthly quota"
                  value={
                    typeof entitlements?.monthly_class_quota === "number"
                      ? quotaLabel(entitlements.monthly_class_quota)
                      : "—"
                  }
                />
                <BriefStat label="Class balance" value={remaining} />
              </div>

              <div className="space-y-5 p-5">
                {(briefing.warnings.length > 0 || !briefing.member.active) && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
                    <div className="flex items-center gap-2 font-semibold">
                      <ShieldAlert className="h-4 w-4" aria-hidden />
                      Attention needed
                    </div>
                    <ul className="mt-2 list-disc space-y-1 pl-5">
                      {!briefing.member.active && <li>This account is inactive.</li>}
                      {briefing.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                    </ul>
                  </div>
                )}

                <Detail
                  icon={<UserRound className="h-4 w-4" />}
                  label="Trainer"
                  value={briefing.trainer_name ?? "Not assigned"}
                />
                <Detail
                  icon={<Clock3 className="h-4 w-4" />}
                  label="Last check-in"
                  value={
                    briefing.last_check_in
                      ? classTime(briefing.last_check_in.checked_in_at)
                      : "No previous check-in"
                  }
                />

                {briefing.upcoming_classes.length > 0 && (
                  <div>
                    <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                      <CalendarDays className="h-4 w-4" aria-hidden /> Next classes
                    </h3>
                    <ul className="mt-2 space-y-2">
                      {briefing.upcoming_classes.slice(0, 3).map((session) => (
                        <li key={session.id} className="rounded-lg bg-ink-800 px-3 py-2 text-sm">
                          <span className="font-medium text-white">{session.name}</span>
                          <span className="block text-xs text-slate-400">{classTime(session.starts_at)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {briefing.active_notices.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Active notices</h3>
                    <ul className="mt-2 space-y-2">
                      {briefing.active_notices.map((notice) => (
                        <li key={notice.id} className="rounded-lg border border-white/8 p-3">
                          <p className="text-sm font-semibold text-white">{notice.title}</p>
                          <p className="mt-1 text-xs leading-relaxed text-slate-400">
                            {notice.message}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3 pt-2">
                  <Button
                    onClick={() => void confirm()}
                    busy={checkingIn}
                    disabled={!briefing.member.active}
                  >
                    <CheckCircle2 className="h-4 w-4" aria-hidden />
                    Confirm
                  </Button>
                  <Button variant="danger" onClick={() => void restart()} disabled={checkingIn}>
                    <XCircle className="h-4 w-4" aria-hidden />
                    Reject
                  </Button>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function BriefStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ink-900 p-4">
      <p className="text-[11px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white">{value}</p>
    </div>
  );
}

function Detail({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-volt-400">{icon}</span>
      <div>
        <p className="text-[11px] uppercase tracking-wider text-slate-500">{label}</p>
        <p className="text-sm font-medium text-white">{value}</p>
      </div>
    </div>
  );
}
