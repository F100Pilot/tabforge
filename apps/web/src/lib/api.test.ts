import { describe, expect, it } from "vitest";
import {
  ProblemError,
  ResponseShapeError,
  parseJob,
  parseProblem,
  parseTab,
  parseUploadTicket,
} from "./api";
import { checkFile, MAX_UPLOAD_BYTES } from "./file-checks";

const job = {
  id: "j1",
  status: "running",
  stage: "separating",
  attempts: 1,
  error_code: null,
  tab_id: null,
  created_at: "2026-11-04T10:00:00Z",
  updated_at: "2026-11-04T10:00:01Z",
};
const tab = {
  id: "t1",
  title: "Teste",
  tuning: ["E4"],
  visibility: "private",
  created_at: "2026-11-04T10:00:00Z",
  revision: { id: "r1", source: "ai", created_at: "2026-11-04T10:00:00Z", score: {} },
  alphatex: "\\title \"x\" . 0.6.4",
};

describe("parseJob", () => {
  it("accepts a valid job", () => expect(parseJob(job).status).toBe("running"));
  it("rejects unknown status", () =>
    expect(() => parseJob({ ...job, status: "weird" })).toThrow(ResponseShapeError));
  it("rejects unknown stage", () =>
    expect(() => parseJob({ ...job, stage: "x" })).toThrow(ResponseShapeError));
  it("rejects non-objects", () => expect(() => parseJob(null)).toThrow(ResponseShapeError));
});

describe("parseTab", () => {
  it("accepts a valid tab", () => expect(parseTab(tab).alphatex).toContain("title"));
  it("rejects missing alphatex", () =>
    expect(() => parseTab({ ...tab, alphatex: 1 })).toThrow(ResponseShapeError));
  it("rejects bad revision source", () =>
    expect(() => parseTab({ ...tab, revision: { ...tab.revision, source: "bot" } })).toThrow(
      ResponseShapeError,
    ));
});

describe("parseUploadTicket", () => {
  const t = {
    audio_id: "a",
    upload_url: "http://s3/x",
    method: "PUT",
    headers: { "Content-Type": "audio/mpeg" },
    expires_in_s: 300,
  };
  it("accepts valid", () => expect(parseUploadTicket(t).audio_id).toBe("a"));
  it("rejects non-PUT", () =>
    expect(() => parseUploadTicket({ ...t, method: "POST" })).toThrow(ResponseShapeError));
  it("rejects non-string headers", () =>
    expect(() => parseUploadTicket({ ...t, headers: { a: 1 } })).toThrow(ResponseShapeError));
});

describe("parseProblem", () => {
  it("maps problem+json", () => {
    const e = parseProblem(413, { type: "t", title: "Big", status: 413, detail: "Grande", code: "file_too_large" });
    expect(e).toBeInstanceOf(ProblemError);
    expect(e.code).toBe("file_too_large");
    expect(e.message).toBe("Grande");
  });
  it("falls back for non-problem bodies", () => {
    const e = parseProblem(502, "<html>");
    expect(e.code).toBe("unknown_error");
    expect(e.status).toBe(502);
  });
});

describe("checkFile", () => {
  it("accepts mp3", () => expect(checkFile({ type: "audio/mpeg", size: 10 })).toBeNull());
  it("rejects unsupported type", () =>
    expect(checkFile({ type: "video/mp4", size: 10 })).toMatch(/Formato/));
  it("rejects empty", () => expect(checkFile({ type: "audio/wav", size: 0 })).toMatch(/vazio/));
  it("rejects too large", () =>
    expect(checkFile({ type: "audio/flac", size: MAX_UPLOAD_BYTES + 1 })).toMatch(/50 MiB/));
  it("accepts exactly 50 MiB", () =>
    expect(checkFile({ type: "audio/ogg", size: MAX_UPLOAD_BYTES })).toBeNull());
});
