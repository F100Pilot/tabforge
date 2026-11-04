import { parsePublicConfig } from "./config";
import { IS_DESKTOP } from "./desktop";
import { declaredType, type FileLike } from "./file-checks";

export type SourceKind = "mix" | "guitar_stem";
export type JobStatus = "queued" | "running" | "done" | "failed";
export type JobStage = "normalizing" | "separating" | "transcribing" | "arranging";

export interface UploadTicket {
  audio_id: string;
  upload_url: string;
  method: "PUT";
  headers: Record<string, string>;
  expires_in_s: number;
}

export interface Job {
  id: string;
  status: JobStatus;
  stage: JobStage | null;
  attempts: number;
  error_code: string | null;
  tab_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobSummary extends Job {
  source_kind: SourceKind;
  duration_ms: number | null;
  tab_title: string | null;
}

export interface TabSummary {
  id: string;
  title: string;
  tuning: unknown;
  visibility: string;
  created_at: string;
}

export interface ScoreWarning {
  bar: number;
  code: string;
  pitch: number;
}

/** The subset of Score v1/v2 the UI reads. */
export interface ScoreInfo {
  tempo_bpm: number | null;
  time_signature: [number, number] | null;
  warnings: ScoreWarning[];
}

export interface Tab {
  id: string;
  title: string;
  tuning: unknown;
  visibility: string;
  created_at: string;
  revision: { id: string; source: "ai" | "user"; created_at: string; score: unknown };
  alphatex: string;
}

/** RFC 9457 problem+json error; `detail` is user-facing, branch on `code`. */
export class ProblemError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  constructor(init: { status: number; code: string; title: string; detail: string }) {
    super(init.detail);
    this.name = "ProblemError";
    this.status = init.status;
    this.code = init.code;
    this.title = init.title;
  }
}

export class ResponseShapeError extends Error {
  constructor(what: string) {
    super(`Resposta inesperada do servidor (${what}).`);
    this.name = "ResponseShapeError";
  }
}

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isNullableStr = (v: unknown): v is string | null => v === null || isStr(v);
const JOB_STATUSES: readonly string[] = ["queued", "running", "done", "failed"];
const JOB_STAGES: readonly string[] = ["normalizing", "separating", "transcribing", "arranging"];

export function parseUploadTicket(v: unknown): UploadTicket {
  if (
    !isRec(v) ||
    !isStr(v.audio_id) ||
    !isStr(v.upload_url) ||
    v.method !== "PUT" ||
    !isRec(v.headers) ||
    !Object.values(v.headers).every(isStr) ||
    typeof v.expires_in_s !== "number"
  ) {
    throw new ResponseShapeError("upload");
  }
  return v as unknown as UploadTicket;
}

export function parseJob(v: unknown): Job {
  if (
    !isRec(v) ||
    !isStr(v.id) ||
    !isStr(v.status) ||
    !JOB_STATUSES.includes(v.status) ||
    !(v.stage === null || (isStr(v.stage) && JOB_STAGES.includes(v.stage))) ||
    typeof v.attempts !== "number" ||
    !isNullableStr(v.error_code) ||
    !isNullableStr(v.tab_id) ||
    !isStr(v.created_at) ||
    !isStr(v.updated_at)
  ) {
    throw new ResponseShapeError("job");
  }
  return v as unknown as Job;
}

export function parseTab(v: unknown): Tab {
  if (
    !isRec(v) ||
    !isStr(v.id) ||
    !isStr(v.title) ||
    !isStr(v.visibility) ||
    !isStr(v.created_at) ||
    !isStr(v.alphatex) ||
    !isRec(v.revision) ||
    !isStr(v.revision.id) ||
    (v.revision.source !== "ai" && v.revision.source !== "user") ||
    !isStr(v.revision.created_at)
  ) {
    throw new ResponseShapeError("tab");
  }
  return v as unknown as Tab;
}

export function parseJobSummary(v: unknown): JobSummary {
  const job = parseJob(v);
  const r = v as Rec;
  if (
    (r.source_kind !== "mix" && r.source_kind !== "guitar_stem") ||
    !(r.duration_ms === null || typeof r.duration_ms === "number") ||
    !isNullableStr(r.tab_title)
  ) {
    throw new ResponseShapeError("job summary");
  }
  return { ...job, source_kind: r.source_kind, duration_ms: r.duration_ms, tab_title: r.tab_title };
}

export function parseJobList(v: unknown): JobSummary[] {
  if (!isRec(v) || !Array.isArray(v.items)) throw new ResponseShapeError("job list");
  return v.items.map(parseJobSummary);
}

export function parseTabSummary(v: unknown): TabSummary {
  if (
    !isRec(v) ||
    !isStr(v.id) ||
    !isStr(v.title) ||
    !isStr(v.visibility) ||
    !isStr(v.created_at)
  ) {
    throw new ResponseShapeError("tab summary");
  }
  return v as unknown as TabSummary;
}

export function parseTabList(v: unknown): TabSummary[] {
  if (!isRec(v) || !Array.isArray(v.items)) throw new ResponseShapeError("tab list");
  return v.items.map(parseTabSummary);
}

/** Tolerant reader for the score fields the viewer shows; unknown/missing fields degrade to null/[]. */
export function readScoreInfo(score: unknown): ScoreInfo {
  const r = isRec(score) ? score : {};
  const ts = r.time_signature;
  const timeSig =
    Array.isArray(ts) &&
    ts.length === 2 &&
    typeof ts[0] === "number" &&
    typeof ts[1] === "number" &&
    ts[0] > 0 &&
    ts[1] > 0
      ? ([ts[0], ts[1]] as [number, number])
      : null;
  const warnings = Array.isArray(r.warnings)
    ? r.warnings.filter(
        (w): w is ScoreWarning =>
          isRec(w) && typeof w.bar === "number" && isStr(w.code) && typeof w.pitch === "number",
      )
    : [];
  return {
    tempo_bpm: typeof r.tempo_bpm === "number" && r.tempo_bpm > 0 ? r.tempo_bpm : null,
    time_signature: timeSig,
    warnings,
  };
}

export function parseProblem(status: number, body: unknown): ProblemError {
  if (isRec(body) && isStr(body.detail) && isStr(body.code)) {
    return new ProblemError({
      status,
      code: body.code,
      title: isStr(body.title) ? body.title : "",
      detail: body.detail,
    });
  }
  return new ProblemError({
    status,
    code: "unknown_error",
    title: "",
    detail: `Pedido falhou (HTTP ${status}).`,
  });
}

export function apiBaseUrl(): URL {
  // Desktop: same origin; src/proxy.ts forwards /v1 to the API on whatever port it got.
  if (IS_DESKTOP && typeof window !== "undefined") return new URL(window.location.origin);
  // Must reference process.env.NEXT_PUBLIC_API_URL literally so Next inlines it.
  return parsePublicConfig({ NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL }).apiBaseUrl;
}

export interface SessionUser {
  id: string;
  email: string;
}

export interface Session {
  user: SessionUser;
  csrf_token: string | null;
}

const UNSAFE_METHODS: readonly string[] = ["POST", "PUT", "PATCH", "DELETE"];

/** Adds `X-CSRF-Token` on unsafe methods when a token is known; never mutates `base`. */
export function csrfHeaders(method: string, base: HeadersInit | undefined, token: string | null): Headers {
  const headers = new Headers(base);
  if (token !== null && UNSAFE_METHODS.includes(method.toUpperCase())) {
    headers.set("X-CSRF-Token", token);
  }
  return headers;
}

let csrfToken: string | null = null;

/** Called with the `csrf_token` from every session/verify response (null clears it). */
export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

/** True for the API's 401 `unauthenticated` problem (also any 401). */
export function isUnauthenticated(err: unknown): boolean {
  return err instanceof ProblemError && err.status === 401;
}

export function parseSession(v: unknown): Session {
  if (
    !isRec(v) ||
    !isRec(v.user) ||
    !isStr(v.user.id) ||
    !isStr(v.user.email) ||
    !isNullableStr(v.csrf_token ?? null)
  ) {
    throw new ResponseShapeError("session");
  }
  return { user: { id: v.user.id, email: v.user.email }, csrf_token: (v.csrf_token as string | null | undefined) ?? null };
}

/** Accepts any JSON object (the 202 body is `{}`); rejects anything else. */
export function parseEmptyObject(v: unknown, what: string): void {
  if (v !== undefined && !isRec(v)) throw new ResponseShapeError(what);
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const method = init?.method ?? "GET";
  const res = await fetch(new URL(path, apiBaseUrl()), {
    cache: "no-store",
    ...init,
    credentials: "include",
    headers: csrfHeaders(method, init?.headers, csrfToken),
  });
  let body: unknown = undefined;
  try {
    body = await res.json();
  } catch {
    body = undefined;
  }
  if (!res.ok) throw parseProblem(res.status, body);
  return body;
}

export async function createUpload(file: FileLike, kind: SourceKind) {
  return parseUploadTicket(
    await request("/v1/uploads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content_type: declaredType(file),
        size_bytes: file.size,
        source_kind: kind,
      }),
    }),
  );
}

/** PUT directly to object storage with exactly the signed headers. */
export async function putFile(ticket: UploadTicket, file: Blob): Promise<void> {
  let res: Response;
  try {
    res = await fetch(ticket.upload_url, { method: "PUT", headers: ticket.headers, body: file });
  } catch {
    throw new ProblemError({
      status: 0,
      code: "upload_network_error",
      title: "",
      detail: "Falha de rede ao enviar o ficheiro. Tente novamente.",
    });
  }
  if (!res.ok) {
    throw new ProblemError({
      status: res.status,
      code: "upload_rejected",
      title: "",
      detail: `O armazenamento recusou o ficheiro (HTTP ${res.status}).`,
    });
  }
}

export async function completeUpload(audioId: string) {
  return parseJob(
    await request(`/v1/uploads/${encodeURIComponent(audioId)}/complete`, { method: "POST" }),
  );
}

export async function getJob(id: string, signal?: AbortSignal) {
  return parseJob(await request(`/v1/jobs/${encodeURIComponent(id)}`, { signal }));
}

export async function getTab(id: string, signal?: AbortSignal) {
  return parseTab(await request(`/v1/tabs/${encodeURIComponent(id)}`, { signal }));
}

export async function listJobs(limit: number, signal?: AbortSignal) {
  return parseJobList(await request(`/v1/jobs?limit=${encodeURIComponent(String(limit))}`, { signal }));
}

export async function listTabs(limit: number, signal?: AbortSignal) {
  return parseTabList(await request(`/v1/tabs?limit=${encodeURIComponent(String(limit))}`, { signal }));
}

export interface RevisionSummary {
  id: string;
  source: "ai" | "user";
  created_at: string;
}

export function parseRevisionList(v: unknown): RevisionSummary[] {
  if (!isRec(v) || !Array.isArray(v.items)) throw new ResponseShapeError("revision list");
  return v.items.map((it) => {
    if (!isRec(it) || !isStr(it.id) || (it.source !== "ai" && it.source !== "user") || !isStr(it.created_at)) {
      throw new ResponseShapeError("revision");
    }
    return { id: it.id, source: it.source, created_at: it.created_at };
  });
}

export function parsePreview(v: unknown): string {
  if (!isRec(v) || !isStr(v.alphatex)) throw new ResponseShapeError("preview");
  return v.alphatex;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

/** Server-side alphaTex for an edited score (also validates it: 422 `validation_error`). */
export async function previewScore(tabId: string, score: unknown, signal?: AbortSignal) {
  return parsePreview(
    await request(`/v1/tabs/${encodeURIComponent(tabId)}/preview`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ score }),
      signal,
    }),
  );
}

/** Saves a new current revision. 409 `revision_conflict` when `baseRevisionId` is no longer current. */
export async function saveRevision(tabId: string, baseRevisionId: string, score: unknown) {
  return parseTab(
    await request(`/v1/tabs/${encodeURIComponent(tabId)}/revisions`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ base_revision_id: baseRevisionId, score }),
    }),
  );
}

export async function listRevisions(tabId: string, signal?: AbortSignal) {
  return parseRevisionList(await request(`/v1/tabs/${encodeURIComponent(tabId)}/revisions`, { signal }));
}

/** Asks for a login link by email. Always resolves for a valid address (the API never reveals if it exists). */
export async function requestMagicLink(email: string): Promise<void> {
  parseEmptyObject(
    await request("/v1/auth/magic-link", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ email }),
    }),
    "magic-link",
  );
}

/** Exchanges the emailed token for a session cookie. 400 `invalid_token` when expired/used/unknown. */
export async function verifyLogin(token: string): Promise<Session> {
  const session = parseSession(
    await request("/v1/auth/verify", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ token }),
    }),
  );
  setCsrfToken(session.csrf_token);
  return session;
}

/** Desktop build: exchanges the launcher's per-start token for the session (ADR-0008). */
export async function desktopLogin(token: string): Promise<Session> {
  const session = parseSession(
    await request("/v1/auth/desktop", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ token }),
    }),
  );
  setCsrfToken(session.csrf_token);
  return session;
}

/** Current session, or null when anonymous (401). */
export async function getSession(signal?: AbortSignal): Promise<Session | null> {
  try {
    const session = parseSession(await request("/v1/auth/session", { signal }));
    setCsrfToken(session.csrf_token);
    return session;
  } catch (err) {
    if (isUnauthenticated(err)) {
      setCsrfToken(null);
      return null;
    }
    throw err;
  }
}

export async function logout(): Promise<void> {
  await request("/v1/auth/logout", { method: "POST" });
  setCsrfToken(null);
}

/** Permanently deletes the account, audio and tabs. 503 `storage_unavailable` → retry later. */
export async function deleteAccount(): Promise<void> {
  await request("/v1/me", { method: "DELETE" });
  setCsrfToken(null);
}

// --- ADR-0009: comparison with the right tab ---

export interface ReferenceNoteInput {
  onset: number;
  pitch: number;
  string: number;
  fret: number;
  bar: number;
}

export interface ReferenceSummary {
  filename: string;
  track: string;
  notes: number;
  created_at: string;
}

export interface BarComparison {
  bar: number;
  reference_notes: number;
  matched: number;
  positions_ok: number;
}

export interface Comparison {
  revision_id: string;
  shift_quarters: number;
  scale: number;
  matched: number;
  ai_notes: number;
  reference_notes: number;
  recall: number;
  precision: number;
  f1: number;
  position_accuracy: number | null;
  onset_error: number | null;
  bars: BarComparison[];
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isNullableNum = (v: unknown): v is number | null => v === null || isNum(v);

export function parseReferenceSummary(v: unknown): ReferenceSummary {
  if (!isRec(v) || !isStr(v.filename) || !isStr(v.track) || !isNum(v.notes) || !isStr(v.created_at)) {
    throw new ResponseShapeError("reference");
  }
  return { filename: v.filename, track: v.track, notes: v.notes, created_at: v.created_at };
}

export function parseComparison(v: unknown): Comparison {
  if (
    !isRec(v) ||
    !isStr(v.revision_id) ||
    !isNum(v.shift_quarters) ||
    !isNum(v.scale) ||
    !isNum(v.matched) ||
    !isNum(v.ai_notes) ||
    !isNum(v.reference_notes) ||
    !isNum(v.recall) ||
    !isNum(v.precision) ||
    !isNum(v.f1) ||
    !isNullableNum(v.position_accuracy) ||
    !isNullableNum(v.onset_error) ||
    !Array.isArray(v.bars)
  ) {
    throw new ResponseShapeError("comparison");
  }
  const bars = v.bars.map((b): BarComparison => {
    if (!isRec(b) || !isNum(b.bar) || !isNum(b.reference_notes) || !isNum(b.matched) || !isNum(b.positions_ok)) {
      throw new ResponseShapeError("comparison bar");
    }
    return { bar: b.bar, reference_notes: b.reference_notes, matched: b.matched, positions_ok: b.positions_ok };
  });
  return {
    revision_id: v.revision_id,
    shift_quarters: v.shift_quarters,
    scale: v.scale,
    matched: v.matched,
    ai_notes: v.ai_notes,
    reference_notes: v.reference_notes,
    recall: v.recall,
    precision: v.precision,
    f1: v.f1,
    position_accuracy: v.position_accuracy,
    onset_error: v.onset_error,
    bars,
  };
}

/** Stores the right tab's notes (replaces any previous one). 413 too big, 422 invalid. */
export async function putReference(
  tabId: string,
  body: { filename: string; track: string; notes: ReferenceNoteInput[] },
) {
  return parseReferenceSummary(
    await request(`/v1/tabs/${encodeURIComponent(tabId)}/reference`, {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  );
}

async function nullOnMissingReference<T>(run: () => Promise<T>): Promise<T | null> {
  try {
    return await run();
  } catch (err) {
    if (err instanceof ProblemError && err.status === 404 && err.code === "reference_not_found") return null;
    throw err;
  }
}

/** The stored reference, or null when the tab has none (404 `reference_not_found`). */
export function getReference(tabId: string, signal?: AbortSignal): Promise<ReferenceSummary | null> {
  return nullOnMissingReference(async () =>
    parseReferenceSummary(await request(`/v1/tabs/${encodeURIComponent(tabId)}/reference`, { signal })),
  );
}

export async function deleteReference(tabId: string): Promise<void> {
  await request(`/v1/tabs/${encodeURIComponent(tabId)}/reference`, { method: "DELETE" });
}

/** Comparison of the current revision with the reference, or null when there is no reference. */
export function getComparison(tabId: string, signal?: AbortSignal): Promise<Comparison | null> {
  return nullOnMissingReference(async () =>
    parseComparison(await request(`/v1/tabs/${encodeURIComponent(tabId)}/comparison`, { signal })),
  );
}
