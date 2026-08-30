export type Role = "member" | "trainer" | "reception" | "admin";

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: Role;
  active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: Role;
  full_name: string;
}

export interface Plan {
  id: string;
  name: string;
  tier: string;
  duration_days: number;
  price_paise: number;
  description: string;
  allowed_disciplines: string;
  monthly_class_quota: number;
  personalised_programme: boolean;
  priority_support: boolean;
  active: boolean;
}

export interface Entitlements {
  has_active_membership: boolean;
  plan_name: string | null;
  tier: string | null;
  expires_on: string | null;
  days_remaining: number | null;
  allowed_disciplines: string[];
  monthly_class_quota: number;
  classes_booked_this_month: number;
  personalised_programme: boolean;
  priority_support: boolean;
}

export interface GymClass {
  id: string;
  name: string;
  discipline: string;
  instructor: string;
  starts_at: string;
  capacity: number;
  seats_taken: number;
  seats_left: number;
  booked_by_me: boolean;
}

export interface Person {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: Role;
  active: boolean;
  plan_name: string | null;
  expires_on: string | null;
}

export interface MemberPass {
  token: string;
  qr_payload: string;
  created_at: string;
}

export interface FrontDeskNotice {
  id: string;
  kind: "repair" | "closure" | "info";
  title: string;
  message: string;
  active_from: string;
  active_until: string | null;
  created_at: string;
  updated_at: string;
}

export interface FrontDeskMember {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  active: boolean;
  photo_available: boolean;
}

export interface UpcomingClassBrief {
  id: string;
  name: string;
  discipline: string;
  instructor: string;
  starts_at: string;
}

export interface FrontDeskBriefing {
  member: FrontDeskMember;
  entitlements: Entitlements;
  upcoming_classes: UpcomingClassBrief[];
  trainer_name: string | null;
  active_notices: FrontDeskNotice[];
  last_check_in: Attendance | null;
  warnings: string[];
}

export interface Attendance {
  id: string;
  member_id: string;
  actor_id: string;
  checked_in_at: string;
  method: "qr" | "manual";
  note: string | null;
}

export interface Programme {
  id: string;
  member_id: string;
  trainer_id: string;
  kind: "workout" | "diet";
  title: string;
  content: string;
  active: boolean;
  created_at: string;
}

export interface Profile {
  goal: string | null;
  experience_level: string | null;
  injuries_or_limits: string | null;
  preferred_domains: string | null;
  equipment_access: string | null;
  assigned_trainer_id: string | null;
}

export interface Overview {
  members: number;
  trainers: number;
  admins: number;
  active_memberships: number;
  memberships_sold: number;
  revenue_paise: number;
  class_bookings: number;
}

export interface KnowledgeDoc {
  id: string;
  filename: string;
  discipline: string;
  chunk_count: number;
  ingest_mode?: string;
  created_at: string;
}

export interface MetricTable {
  key: string;
  title: string;
  headline: string;
  columns: string[];
  rows: Record<string, string | number>[];
}

export interface AnalystAnswer {
  question: string;
  answer: string;
  metrics: MetricTable[];
}

export type Priority = "high" | "medium" | "low";

export interface Recommendation {
  priority: Priority;
  category: string;
  title: string;
  evidence: string;
  action: string;
  impact: string;
}

export interface AdvisorReport {
  summary: string;
  briefing: string;
  recommendations: Recommendation[];
}

export interface CopilotAnswer {
  question: string;
  answer: string;
  agents_used: string[];
  metrics: MetricTable[];
  recommendations: Recommendation[];
}

export type ChatAction = "none" | "login" | "signup" | "show_plans" | "upgrade";

export interface ChatReply {
  conversation_id: string;
  answer: string;
  route: string;
  sources: { source: string; page: number | null; excerpt: string | null }[];
  needs_human_handoff: boolean;
  action: ChatAction;
}

const TOKEN_KEY = "mastergym.token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function readDetail(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null) return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors arrive as a list; show the first readable message.
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (typeof first.msg === "string") return first.msg;
  }
  return fallback;
}

// Empty during development, where Vite proxies /api to the local backend. In production the
// site and the API sit on different domains, so the deployed build is given an absolute URL.
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

// The API sleeps after fifteen idle minutes on Render's free plan and takes the best part of
// a minute to come back. Without a word of explanation the first visit of the day just looks
// broken, so anything still waiting after this long announces itself.
const COLD_START_MS = 3000;

let slowRequests = 0;
let serverHasReplied = false;
const coldStartListeners = new Set<(waking: boolean) => void>();

export function onColdStart(listener: (waking: boolean) => void): () => void {
  coldStartListeners.add(listener);
  return () => {
    coldStartListeners.delete(listener);
  };
}

function announceColdStart() {
  const waking = slowRequests > 0;
  coldStartListeners.forEach((listener) => listener(waking));
}

/** Returns the function that stops watching this request. */
function watchColdStart(): () => void {
  if (serverHasReplied) return () => {};
  let counted = false;
  const timer = setTimeout(() => {
    counted = true;
    slowRequests += 1;
    announceColdStart();
  }, COLD_START_MS);

  return () => {
    clearTimeout(timer);
    if (!counted) return;
    slowRequests -= 1;
    announceColdStart();
  };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get();
  const isFormData = init.body instanceof FormData;
  const stopWatching = watchColdStart();

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api${path}`, {
      ...init,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    });
    // Any reply, including an error, means the machine is up and later calls are fast.
    serverHasReplied = true;
  } finally {
    stopWatching();
  }

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) tokenStore.clear();
    throw new ApiError(response.status, readDetail(body, "Something went wrong. Please try again."));
  }
  return body as T;
}

async function requestBlob(path: string): Promise<Blob> {
  const token = tokenStore.get();
  const response = await fetch(`${API_BASE}/api${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 401) tokenStore.clear();
    throw new ApiError(response.status, readDetail(body, "Could not load this image."));
  }
  return response.blob();
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const put = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const remove = <T,>(path: string) => request<T>(path, { method: "DELETE" });

export const api = {
  health: () => get<{ status: string; app: string; bot: string }>("/health"),

  login: (email: string, password: string) =>
    post<TokenResponse>("/auth/login", { email, password }),
  register: (payload: { email: string; full_name: string; password: string; phone?: string }) =>
    post<TokenResponse>("/auth/register", payload),
  me: () => get<User>("/auth/me"),

  plans: () => get<Plan[]>("/plans"),
  entitlements: () => get<Entitlements>("/me/entitlements"),
  buyPlan: (plan_id: string) =>
    post<{ plan_name: string; expires_on: string; message: string }>("/me/membership", { plan_id }),

  classes: () => get<GymClass[]>("/classes"),
  bookClass: (id: string) => post<{ message: string }>(`/classes/${id}/book`),
  cancelBooking: (id: string) => remove<{ message: string }>(`/classes/${id}/book`),
  createClass: (payload: {
    name: string;
    discipline: string;
    instructor: string;
    starts_at: string;
    capacity: number;
  }) => post<{ id: string; message: string }>("/staff/classes", payload),
  deleteClass: (id: string) => remove<{ message: string }>(`/staff/classes/${id}`),

  profile: () => get<Profile>("/me/profile"),
  saveProfile: (payload: Partial<Profile>) => put<Profile>("/me/profile", payload),
  myProgrammes: () => get<Programme[]>("/me/programmes"),

  people: (role?: Role) => get<Person[]>(`/admin/people${role ? `?role=${role}` : ""}`),
  createPerson: (payload: {
    email: string;
    full_name: string;
    password: string;
    role: "member" | "trainer" | "reception";
    phone?: string;
  }) => post<Person>("/admin/people", payload),
  updatePerson: (id: string, payload: { active?: boolean; full_name?: string; phone?: string }) =>
    patch<Person>(`/admin/people/${id}`, payload),
  changeRole: (id: string, role: Role) => post<Person>(`/admin/people/${id}/role`, { role }),
  assignTrainer: (memberId: string, trainerId: string) =>
    post<Profile>(`/admin/people/${memberId}/trainer/${trainerId}`),
  overview: () => get<Overview>("/admin/overview"),

  myPass: () => get<MemberPass>("/me/pass"),
  frontDeskLookup: (token: string) =>
    post<FrontDeskBriefing>("/front-desk/lookup", { token }),
  frontDeskCheckIn: (user_id: string, method: "qr" | "manual") =>
    post<{
      attendance: Attendance;
      already_checked_in: boolean;
      briefing: FrontDeskBriefing;
    }>("/front-desk/check-in", { user_id, method }),
  frontDeskSearch: (query: string) =>
    get<FrontDeskMember[]>(`/front-desk/search?q=${encodeURIComponent(query)}`),
  frontDeskBriefing: (userId: string) =>
    get<FrontDeskBriefing>(`/front-desk/briefing/${userId}`),
  frontDeskNotices: () => get<FrontDeskNotice[]>("/front-desk/notices"),
  createNotice: (payload: {
    kind: FrontDeskNotice["kind"];
    title: string;
    message: string;
    active_from: string;
    active_until: string | null;
  }) => post<FrontDeskNotice>("/front-desk/notices", payload),
  updateNotice: (
    id: string,
    payload: {
      kind: FrontDeskNotice["kind"];
      title: string;
      message: string;
      active_from: string;
      active_until: string | null;
    },
  ) => put<FrontDeskNotice>(`/front-desk/notices/${id}`, payload),
  deleteNotice: (id: string) => remove<{ message: string }>(`/front-desk/notices/${id}`),
  rotateMemberPass: (id: string) =>
    post<MemberPass>(`/staff/members/${id}/pass/rotate`),
  uploadMemberPhoto: (id: string, file: File) => {
    const form = new FormData();
    form.append("photo", file);
    return request<{ member_id: string; content_type: string; size_bytes: number }>(
      `/staff/members/${id}/photo`,
      {
      method: "PUT",
      body: form,
      },
    );
  },
  memberPhoto: (id: string) => requestBlob(`/staff/members/${id}/photo`),

  myMembers: () => get<Person[]>("/trainer/members"),
  memberProgrammes: (memberId: string) => get<Programme[]>(`/staff/members/${memberId}/programmes`),
  createProgramme: (payload: {
    member_id: string;
    kind: "workout" | "diet";
    title: string;
    content: string;
  }) => post<Programme>("/staff/programmes", payload),

  documents: () => get<KnowledgeDoc[]>("/admin/knowledge/documents"),
  uploadDocument: (file: File, discipline: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("discipline", discipline);
    return request<KnowledgeDoc>("/admin/knowledge/documents", { method: "POST", body: form });
  },
  deleteDocument: (id: string) => remove<{ message: string }>(`/admin/knowledge/documents/${id}`),

  chat: (message: string, conversationId: string | null) =>
    post<ChatReply>("/fitbot/chat", { message, conversation_id: conversationId }),

  metrics: () => get<MetricTable[]>("/admin/analyst/metrics"),
  askAnalyst: (question: string) => post<AnalystAnswer>("/admin/analyst/ask", { question }),
  advisorReport: () => get<AdvisorReport>("/admin/advisor/report"),
  askCopilot: (question: string) => post<CopilotAnswer>("/admin/copilot/ask", { question }),
};
