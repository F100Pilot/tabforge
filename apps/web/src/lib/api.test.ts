import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ProblemError,
  ResponseShapeError,
  parseJob,
  parseProblem,
  csrfHeaders,
  getSession,
  isUnauthenticated,
  parseEmptyObject,
  parseSession,
  parseTab,
  parseUploadTicket,
  setCsrfToken,
  verifyLogin,
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

describe("parseSession", () => {
  it("accepts a session with csrf token", () =>
    expect(parseSession({ user: { id: "u", email: "a@b.pt" }, csrf_token: "c" }).csrf_token).toBe("c"));
  it("accepts null or missing csrf token as null", () => {
    expect(parseSession({ user: { id: "u", email: "a@b.pt" }, csrf_token: null }).csrf_token).toBeNull();
    expect(parseSession({ user: { id: "u", email: "a@b.pt" } }).csrf_token).toBeNull();
  });
  it("rejects bad shapes", () => {
    expect(() => parseSession({ user: { id: "u" }, csrf_token: null })).toThrow(ResponseShapeError);
    expect(() => parseSession({ user: { id: "u", email: "e" }, csrf_token: 3 })).toThrow(ResponseShapeError);
    expect(() => parseSession(null)).toThrow(ResponseShapeError);
  });
});

describe("parseEmptyObject", () => {
  it("accepts {} and empty body", () => {
    expect(() => parseEmptyObject({}, "x")).not.toThrow();
    expect(() => parseEmptyObject(undefined, "x")).not.toThrow();
  });
  it("rejects non-objects", () => expect(() => parseEmptyObject("x", "x")).toThrow(ResponseShapeError));
});

describe("csrfHeaders", () => {
  it("adds the token on unsafe methods", () => {
    for (const m of ["POST", "put", "PATCH", "DELETE"]) {
      expect(csrfHeaders(m, undefined, "tok").get("X-CSRF-Token")).toBe("tok");
    }
  });
  it("does not add it on safe methods or without a token", () => {
    expect(csrfHeaders("GET", undefined, "tok").has("X-CSRF-Token")).toBe(false);
    expect(csrfHeaders("POST", undefined, null).has("X-CSRF-Token")).toBe(false);
  });
  it("keeps existing headers", () =>
    expect(csrfHeaders("POST", { "Content-Type": "application/json" }, "t").get("Content-Type")).toBe(
      "application/json",
    ));
});

describe("isUnauthenticated", () => {
  const mk = (status: number) => new ProblemError({ status, code: "x", title: "", detail: "d" });
  it("matches 401 problems only", () => {
    expect(isUnauthenticated(mk(401))).toBe(true);
    expect(isUnauthenticated(mk(403))).toBe(false);
    expect(isUnauthenticated(new Error("x"))).toBe(false);
  });
});

describe("session requests", () => {
  beforeEach(() => vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000"));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    setCsrfToken(null);
  });
  const json = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  it("getSession returns null on 401 and sends credentials", async () => {
    const f = vi.fn().mockResolvedValue(json(401, { code: "unauthenticated", detail: "x" }));
    vi.stubGlobal("fetch", f);
    expect(await getSession()).toBeNull();
    expect(f.mock.calls[0][1].credentials).toBe("include");
  });

  it("getSession rethrows other errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(500, { code: "boom", detail: "x" })));
    await expect(getSession()).rejects.toBeInstanceOf(ProblemError);
  });

  it("verifyLogin stores the csrf token used by later unsafe requests", async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(json(200, { user: { id: "u", email: "a@b.pt" }, csrf_token: "tok1" }))
      .mockResolvedValueOnce(json(200, { user: { id: "u", email: "a@b.pt" }, csrf_token: "tok1" }));
    vi.stubGlobal("fetch", f);
    await verifyLogin("abc");
    await verifyLogin("abc");
    const sent = f.mock.calls[1][1].headers as Headers;
    expect(sent.get("X-CSRF-Token")).toBe("tok1");
    expect((f.mock.calls[0][1].headers as Headers).has("X-CSRF-Token")).toBe(false);
  });
});
