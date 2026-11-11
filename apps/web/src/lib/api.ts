import { parsePublicConfig } from "./config";
import { IS_DESKTOP } from "./desktop";
import { declaredType, type FileLike } from "./file-checks";
import { scoreTracks, type ScoreTrack } from "./tracks";

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

/** The subset of Score v1/v2/v3 the UI reads. `warnings` is the sum over all tracks. */
export interface ScoreInfo {
  tempo_bpm: number | null;
  time_signature: [number, number] | null;
  warnings: ScoreWarning[];
  /** One entry for v1/v2 ("Guitarra"), one per track for v3. */
  tracks: Array<Pick<ScoreTrack, "name" | "tuning" | "warnings">>;
}

/** Where a revision came from: the transcription, the user's edit, or re-fretting with the
 * learned weights (ADR-0016). */
export type RevisionSource = "ai" | "user" | "learned";
const isRevisionSource = (v: unknown): v is RevisionSource => v === "ai" || v === "user" || v === "learned";

export interface Tab {
  id: string;
  title: string;
  tuning: unknown;
  visibility: string;
  created_at: string;
  revision: { id: string; source: RevisionSource; created_at: string; score: unknown };
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
    !isRevisionSource(v.revision.source) ||
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
  const tracks = scoreTracks(score).map(({ name, tuning, warnings }) => ({ name, tuning, warnings }));
  const warnings = tracks.flatMap((t) => t.warnings);
  return {
    tempo_bpm: typeof r.tempo_bpm === "number" && r.tempo_bpm > 0 ? r.tempo_bpm : null,
    time_signature: timeSig,
    warnings,
    tracks,
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

export interface YoutubeImport {
  job: Job;
  title: string;
  /** The MP3 copy kept in the music folder, when the desktop configures one. */
  mp3_path: string | null;
}

export function parseYoutubeImport(v: unknown): YoutubeImport {
  if (!isRec(v) || !isStr(v.title) || !isNullableStr(v.mp3_path)) throw new ResponseShapeError("youtube import");
  return { job: parseJob(v.job), title: v.title, mp3_path: v.mp3_path };
}

/** Desktop only (ADR-0014): the API downloads the audio as MP3 and queues the job. */
export async function importYoutube(url: string, kind: SourceKind) {
  return parseYoutubeImport(
    await request("/v1/imports/youtube", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.trim(), source_kind: kind }),
    }),
  );
}

/** Deletes a song (its audio, job and tab); one that is already gone (404) counts as deleted. */
async function deleteSong(path: string): Promise<void> {
  try {
    await request(path, { method: "DELETE" });
  } catch (err) {
    if (err instanceof ProblemError && err.status === 404) return;
    throw err;
  }
}

export function deleteJob(id: string): Promise<void> {
  return deleteSong(`/v1/jobs/${encodeURIComponent(id)}`);
}

export function deleteTab(id: string): Promise<void> {
  return deleteSong(`/v1/tabs/${encodeURIComponent(id)}`);
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
  source: RevisionSource;
  created_at: string;
}

export function parseRevisionList(v: unknown): RevisionSummary[] {
  if (!isRec(v) || !Array.isArray(v.items)) throw new ResponseShapeError("revision list");
  return v.items.map((it) => {
    if (!isRec(it) || !isStr(it.id) || !isRevisionSource(it.source) || !isStr(it.created_at)) {
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
  differences: Differences;
  /** "E standard", "Drop D"...; null from an API older than the tuning check. */
  tab_tuning_name: string | null;
  reference_tuning_name: string | null;
}

export type DifferenceKind = "position" | "missing" | "extra" | "timing";
export const DIFFERENCE_KINDS: DifferenceKind[] = ["position", "missing", "extra", "timing"];

export interface Difference {
  kind: DifferenceKind;
  bar: number;
  onset: number;
  pitch: number;
  ai: { string: number; fret: number; bar: number; beat: number } | null;
  ref: { string: number; fret: number } | null;
  onset_error: number | null;
}

export interface Differences {
  counts: Record<DifferenceKind, number>;
  items: Difference[];
  truncated: boolean;
}

export interface AppliedCorrections {
  tab: Tab;
  applied: number;
  skipped: number;
  /** The track took the correct tab's tuning (its name). */
  retuned_to: string | null;
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isNullableNum = (v: unknown): v is number | null => v === null || isNum(v);

export function parseReferenceSummary(v: unknown): ReferenceSummary {
  if (!isRec(v) || !isStr(v.filename) || !isStr(v.track) || !isNum(v.notes) || !isStr(v.created_at)) {
    throw new ResponseShapeError("reference");
  }
  return { filename: v.filename, track: v.track, notes: v.notes, created_at: v.created_at };
}

export const NO_DIFFERENCES: Differences = {
  counts: { position: 0, missing: 0, extra: 0, timing: 0 },
  items: [],
  truncated: false,
};

/** `undefined` (older API without `differences`) means none; anything else must be well formed. */
export function parseDifferences(v: unknown): Differences {
  if (v === undefined) return { ...NO_DIFFERENCES, counts: { ...NO_DIFFERENCES.counts }, items: [] };
  if (!isRec(v) || !isRec(v.counts) || !Array.isArray(v.items) || typeof v.truncated !== "boolean") {
    throw new ResponseShapeError("differences");
  }
  const counts = {} as Record<DifferenceKind, number>;
  for (const k of DIFFERENCE_KINDS) {
    const n = (v.counts as Rec)[k];
    if (!isNum(n) || !Number.isInteger(n) || n < 0) throw new ResponseShapeError("differences counts");
    counts[k] = n;
  }
  const items = v.items.map((d): Difference => {
    if (
      !isRec(d) ||
      typeof d.kind !== "string" ||
      !(DIFFERENCE_KINDS as string[]).includes(d.kind) ||
      !isNum(d.bar) ||
      !isNum(d.onset) ||
      !isNum(d.pitch) ||
      !isNullableNum(d.onset_error ?? null)
    ) {
      throw new ResponseShapeError("difference");
    }
    const ai = d.ai ?? null;
    if (
      ai !== null &&
      !(isRec(ai) && isNum(ai.string) && isNum(ai.fret) && isNum(ai.bar) && isNum(ai.beat))
    ) {
      throw new ResponseShapeError("difference ai");
    }
    const ref = d.ref ?? null;
    if (ref !== null && !(isRec(ref) && isNum(ref.string) && isNum(ref.fret))) {
      throw new ResponseShapeError("difference ref");
    }
    return {
      kind: d.kind as DifferenceKind,
      bar: d.bar,
      onset: d.onset,
      pitch: d.pitch,
      ai: ai && { string: (ai as Rec).string as number, fret: (ai as Rec).fret as number, bar: (ai as Rec).bar as number, beat: (ai as Rec).beat as number },
      ref: ref && { string: (ref as Rec).string as number, fret: (ref as Rec).fret as number },
      onset_error: (d.onset_error as number | null | undefined) ?? null,
    };
  });
  return { counts, items, truncated: v.truncated };
}

export function parseAppliedCorrections(v: unknown): AppliedCorrections {
  if (!isRec(v) || !isNum(v.applied) || !isNum(v.skipped)) throw new ResponseShapeError("corrections");
  return {
    tab: parseTab(v.tab),
    applied: v.applied,
    skipped: v.skipped,
    retuned_to: isStr(v.retuned_to) ? v.retuned_to : null,
  };
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
    differences: parseDifferences(v.differences),
    tab_tuning_name: isStr(v.tab_tuning_name) ? v.tab_tuning_name : null,
    reference_tuning_name: isStr(v.reference_tuning_name) ? v.reference_tuning_name : null,
  };
}

/** Stores the right tab's notes (replaces any previous one). 413 too big, 422 invalid. */
export async function putReference(
  tabId: string,
  body: { filename: string; track: string; notes: ReferenceNoteInput[] },
  trackIndex = 0,
) {
  return parseReferenceSummary(
    await request(referencePath(tabId, trackIndex), {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  );
}

/** `?track=N` is the tab's track (ADR-0010); track 0 is the default and keeps the plain URL. */
function trackQuery(trackIndex: number): string {
  return trackIndex > 0 ? `?track=${encodeURIComponent(String(trackIndex))}` : "";
}

function referencePath(tabId: string, trackIndex: number): string {
  return `/v1/tabs/${encodeURIComponent(tabId)}/reference${trackQuery(trackIndex)}`;
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
export function getReference(tabId: string, trackIndex = 0, signal?: AbortSignal): Promise<ReferenceSummary | null> {
  return nullOnMissingReference(async () =>
    parseReferenceSummary(await request(referencePath(tabId, trackIndex), { signal })),
  );
}

export async function deleteReference(tabId: string, trackIndex = 0): Promise<void> {
  await request(referencePath(tabId, trackIndex), { method: "DELETE" });
}

/** Comparison of the current revision with the reference, or null when there is no reference. */
export function getComparison(tabId: string, trackIndex = 0, signal?: AbortSignal): Promise<Comparison | null> {
  return nullOnMissingReference(async () =>
    parseComparison(await request(`/v1/tabs/${encodeURIComponent(tabId)}/comparison${trackQuery(trackIndex)}`, { signal })),
  );
}

/**
 * Applies the detected corrections of the given kinds as a new revision (only `position` today).
 * 409 `revision_conflict` when `baseRevisionId` is no longer current; 200 with `applied: 0` creates nothing.
 */
export async function applyCorrections(
  tabId: string,
  trackIndex: number,
  baseRevisionId: string,
  kinds: DifferenceKind[],
): Promise<AppliedCorrections> {
  return parseAppliedCorrections(
    await request(`/v1/tabs/${encodeURIComponent(tabId)}/comparison/apply${trackQuery(trackIndex)}`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ base_revision_id: baseRevisionId, kinds }),
    }),
  );
}

export interface Refretted {
  tab: Tab;
  /** Attacked notes now on another string or fret; 0 means no new revision. */
  changed: number;
}

export function parseRefretted(v: unknown): Refretted {
  if (!isRec(v) || !isNum(v.changed)) throw new ResponseShapeError("refret");
  return { tab: parseTab(v.tab), changed: v.changed };
}

/** ADR-0016: place every track again with the learned weights, as a new revision. */
export async function refretTab(tabId: string, baseRevisionId: string): Promise<Refretted> {
  return parseRefretted(
    await request(`/v1/tabs/${encodeURIComponent(tabId)}/refret`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ base_revision_id: baseRevisionId }),
    }),
  );
}

export type TuningStatus = "none" | "stale" | "ready" | "insufficient";
const TUNING_STATUSES: readonly string[] = ["none", "stale", "ready", "insufficient"];
export const WEIGHT_KEYS = ["span", "height", "move", "open_move"] as const;
export type TuningWeights = Record<(typeof WEIGHT_KEYS)[number], number>;

/** ADR-0011: the user's learned fretting profile. */
export interface Tuning {
  status: TuningStatus;
  tabs: number;
  notes: number;
  default_accuracy: number | null;
  tuned_accuracy: number | null;
  in_use: boolean;
  weights: TuningWeights | null;
  updated_at: string | null;
  min_notes: number;
  min_tabs: number;
}

export function parseTuning(v: unknown): Tuning {
  if (
    !isRec(v) ||
    !isStr(v.status) ||
    !TUNING_STATUSES.includes(v.status) ||
    !isNum(v.tabs) ||
    !isNum(v.notes) ||
    !isNullableNum(v.default_accuracy) ||
    !isNullableNum(v.tuned_accuracy) ||
    typeof v.in_use !== "boolean" ||
    !isNullableStr(v.updated_at) ||
    !isNum(v.min_notes) ||
    !isNum(v.min_tabs)
  ) {
    throw new ResponseShapeError("aprendizagem");
  }
  let weights: TuningWeights | null = null;
  if (v.weights !== null) {
    const w = v.weights;
    if (!isRec(w) || !WEIGHT_KEYS.every((k) => isNum(w[k]))) throw new ResponseShapeError("aprendizagem");
    weights = { span: w.span as number, height: w.height as number, move: w.move as number, open_move: w.open_move as number };
  }
  return {
    status: v.status as TuningStatus,
    tabs: v.tabs,
    notes: v.notes,
    default_accuracy: v.default_accuracy,
    tuned_accuracy: v.tuned_accuracy,
    in_use: v.in_use,
    weights,
    updated_at: v.updated_at,
    min_notes: v.min_notes,
    min_tabs: v.min_tabs,
  };
}

export async function getTuning(signal?: AbortSignal): Promise<Tuning> {
  return parseTuning(await request("/v1/me/tuning", { signal }));
}

/** "Atualizar agora": marks the profile stale for the worker (202, same body). */
export async function requestTuning(): Promise<Tuning> {
  return parseTuning(await request("/v1/me/tuning", { method: "POST" }));
}
