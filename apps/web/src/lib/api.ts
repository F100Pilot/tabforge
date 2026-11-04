import { parsePublicConfig } from "./config";
import { declaredType, type FileLike } from "./file-checks";

export type SourceKind = "mix" | "guitar_stem";
export type JobStatus = "queued" | "running" | "done" | "failed";
export type JobStage = "separating" | "transcribing" | "arranging";

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
const JOB_STAGES: readonly string[] = ["separating", "transcribing", "arranging"];

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
  // Must reference process.env.NEXT_PUBLIC_API_URL literally so Next inlines it.
  return parsePublicConfig({ NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL }).apiBaseUrl;
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const res = await fetch(new URL(path, apiBaseUrl()), { cache: "no-store", ...init });
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
