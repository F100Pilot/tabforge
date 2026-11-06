import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ProblemError,
  ResponseShapeError,
  parseJob,
  parseProblem,
  csrfHeaders,
  getSession,
  applyCorrections,
  parseDifferences,
  getComparison,
  getReference,
  putReference,
  deleteReference,
  parseComparison,
  isUnauthenticated,
  parseEmptyObject,
  parseSession,
  parseTab,
  parseTuning,
  getTuning,
  requestTuning,
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

const comparison = {
  revision_id: "r1",
  shift_quarters: 4,
  scale: 1,
  matched: 8,
  ai_notes: 10,
  reference_notes: 12,
  recall: 0.667,
  precision: 0.8,
  f1: 0.727,
  position_accuracy: null,
  onset_error: 0.1,
  bars: [{ bar: 1, reference_notes: 4, matched: 3, positions_ok: 2 }],
};

describe("parseComparison", () => {
  it("accepts a valid comparison, including null position accuracy", () => {
    expect(parseComparison(comparison).bars[0].matched).toBe(3);
  });
  it("reads the tunings, null from an older API", () => {
    expect(parseComparison(comparison).tab_tuning_name).toBeNull();
    const c = parseComparison({ ...comparison, tab_tuning_name: "E standard", reference_tuning_name: "Drop D" });
    expect([c.tab_tuning_name, c.reference_tuning_name]).toEqual(["E standard", "Drop D"]);
  });
  it("rejects missing fields and bad bars", () => {
    expect(() => parseComparison({ ...comparison, recall: "x" })).toThrow(ResponseShapeError);
    expect(() => parseComparison({ ...comparison, bars: [{ bar: 1 }] })).toThrow(ResponseShapeError);
    expect(() => parseComparison(null)).toThrow(ResponseShapeError);
  });
});

const diffs = {
  counts: { position: 1, missing: 2, extra: 0, timing: 1 },
  items: [
    { kind: "position", bar: 2, onset: 5, pitch: 64, ai: { string: 2, fret: 5, bar: 1, beat: 1 }, ref: { string: 1, fret: 0 }, onset_error: null },
    { kind: "missing", bar: 3, onset: 9, pitch: 55, ai: null, ref: { string: 3, fret: 0 }, onset_error: null },
    { kind: "timing", bar: 4, onset: 13, pitch: 62, ai: { string: 3, fret: 7, bar: 3, beat: 0 }, ref: { string: 3, fret: 7 }, onset_error: 0.2 },
  ],
  truncated: false,
};

describe("parseDifferences", () => {
  it("treats a missing field (older API) as none", () => {
    const c = parseComparison(comparison);
    expect(c.differences.items).toEqual([]);
    expect(c.differences.counts).toEqual({ position: 0, missing: 0, extra: 0, timing: 0 });
    expect(c.differences.truncated).toBe(false);
  });
  it("parses items", () => {
    const d = parseComparison({ ...comparison, differences: diffs }).differences;
    expect(d.counts.missing).toBe(2);
    expect(d.items[1].ai).toBeNull();
    expect(d.items[2].onset_error).toBe(0.2);
  });
  it("rejects malformed differences", () => {
    expect(() => parseDifferences(null)).toThrow(ResponseShapeError);
    expect(() => parseDifferences({ ...diffs, truncated: "no" })).toThrow(ResponseShapeError);
    expect(() => parseDifferences({ ...diffs, counts: { position: 1 } })).toThrow(ResponseShapeError);
    expect(() => parseDifferences({ ...diffs, items: [{ ...diffs.items[0], kind: "other" }] })).toThrow(ResponseShapeError);
    expect(() => parseDifferences({ ...diffs, items: [{ ...diffs.items[0], ai: { string: 1 } }] })).toThrow(ResponseShapeError);
  });
});

describe("applyCorrections", () => {
  beforeEach(() => vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000"));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    setCsrfToken(null);
  });
  const json = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  const tab = {
    id: "t1", title: "x", tuning: [], visibility: "private", created_at: "2026-01-01",
    revision: { id: "r2", source: "user", created_at: "2026-01-02", score: {} }, alphatex: "\\title x",
  };

  it("posts base revision and kinds with csrf, ?track only when > 0", async () => {
    setCsrfToken("tok");
    const f = vi.fn().mockImplementation(async () => json(201, { tab, applied: 3, skipped: 1 }));
    vi.stubGlobal("fetch", f);
    const r = await applyCorrections("t1", 0, "r1", ["position"]);
    await applyCorrections("t1", 2, "r1", ["position"]);
    expect(r).toMatchObject({ applied: 3, skipped: 1, retuned_to: null });
    expect(r.tab.revision.id).toBe("r2");
    expect(String(f.mock.calls[0][0])).toMatch(/\/v1\/tabs\/t1\/comparison\/apply$/);
    expect(String(f.mock.calls[1][0])).toMatch(/\/comparison\/apply\?track=2$/);
    const init = f.mock.calls[0][1];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ base_revision_id: "r1", kinds: ["position"] });
    expect((init.headers as Headers).get("X-CSRF-Token")).toBe("tok");
  });
  it("throws ProblemError on 409 and ResponseShapeError on a bad body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(409, { code: "revision_conflict", detail: "x" })));
    await expect(applyCorrections("t1", 0, "r1", ["position"])).rejects.toMatchObject({ status: 409, code: "revision_conflict" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(200, { applied: 0 })));
    await expect(applyCorrections("t1", 0, "r1", ["position"])).rejects.toBeInstanceOf(ResponseShapeError);
  });
});

describe("reference requests", () => {
  beforeEach(() => vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000"));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    setCsrfToken(null);
  });
  const json = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  const missing = () => json(404, { code: "reference_not_found", detail: "Sem tab certa." });

  it("getReference and getComparison return null on 404 reference_not_found", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => missing()));
    expect(await getReference("t1")).toBeNull();
    expect(await getComparison("t1")).toBeNull();
  });

  it("passes the tab track as ?track=N (omitted for track 0)", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => missing());
    vi.stubGlobal("fetch", fetchMock);
    await getReference("t1", 1);
    await getComparison("t1", 1);
    await getReference("t1");
    await deleteReference("t1", 2).catch(() => undefined);
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls[0]).toMatch(/\/v1\/tabs\/t1\/reference\?track=1$/);
    expect(urls[1]).toMatch(/\/v1\/tabs\/t1\/comparison\?track=1$/);
    expect(urls[2]).toMatch(/\/v1\/tabs\/t1\/reference$/);
    expect(urls[3]).toMatch(/\/reference\?track=2$/);
  });

  it("rethrows other 404s", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(404, { code: "not_found", detail: "x" })));
    await expect(getComparison("t1")).rejects.toBeInstanceOf(ProblemError);
  });

  it("putReference sends the notes with the csrf token and parses the summary", async () => {
    setCsrfToken("tok");
    const f = vi
      .fn()
      .mockResolvedValue(json(200, { filename: "a.gp", track: "Guitarra", notes: 1, created_at: "2026-11-04T10:00:00Z" }));
    vi.stubGlobal("fetch", f);
    const out = await putReference("t 1", {
      filename: "a.gp",
      track: "Guitarra",
      notes: [{ onset: 0, pitch: 40, string: 6, fret: 0, bar: 1 }],
    });
    expect(out.notes).toBe(1);
    expect(String(f.mock.calls[0][0])).toBe("http://localhost:8000/v1/tabs/t%201/reference");
    expect(f.mock.calls[0][1].method).toBe("PUT");
    expect((f.mock.calls[0][1].headers as Headers).get("X-CSRF-Token")).toBe("tok");
    expect(JSON.parse(f.mock.calls[0][1].body).notes).toHaveLength(1);
  });

  it("surfaces 413 and 422 as ProblemError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(413, { code: "payload_too_large", detail: "grande" })));
    await expect(putReference("t1", { filename: "a", track: "b", notes: [] })).rejects.toMatchObject({ status: 413 });
  });

  it("deleteReference accepts an empty 204", async () => {
    const f = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", f);
    await expect(deleteReference("t1")).resolves.toBeUndefined();
    expect(f.mock.calls[0][1].method).toBe("DELETE");
  });
});

describe("tuning", () => {
  const body = {
    status: "ready",
    tabs: 3,
    notes: 400,
    default_accuracy: 0.62,
    tuned_accuracy: 0.71,
    in_use: true,
    weights: { span: 1, height: 0.5, move: 2, open_move: 0.3 },
    updated_at: "2026-11-05T10:00:00Z",
    min_notes: 200,
    min_tabs: 2,
  };
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    setCsrfToken(null);
  });

  it("parses a full body and a body without weights", () => {
    expect(parseTuning(body).weights?.open_move).toBe(0.3);
    const none = parseTuning({ ...body, status: "none", weights: null, default_accuracy: null, tuned_accuracy: null, updated_at: null, in_use: false });
    expect(none.weights).toBeNull();
  });
  it("rejects bad shapes", () => {
    expect(() => parseTuning({ ...body, status: "weird" })).toThrow(ResponseShapeError);
    expect(() => parseTuning({ ...body, tabs: "3" })).toThrow(ResponseShapeError);
    expect(() => parseTuning({ ...body, weights: { span: 1 } })).toThrow(ResponseShapeError);
    expect(() => parseTuning({ ...body, in_use: 1 })).toThrow(ResponseShapeError);
    expect(() => parseTuning(null)).toThrow(ResponseShapeError);
  });
  it("getTuning GETs and requestTuning POSTs with the CSRF token", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000");
    setCsrfToken("tok");
    const f = vi.fn().mockImplementation(async () => new Response(JSON.stringify(body), { status: 200 }));
    vi.stubGlobal("fetch", f);
    await getTuning();
    await requestTuning();
    expect(String(f.mock.calls[0][0])).toBe("http://localhost:8000/v1/me/tuning");
    expect(f.mock.calls[1][1].method).toBe("POST");
    expect((f.mock.calls[1][1].headers as Headers).get("X-CSRF-Token")).toBe("tok");
  });
});
