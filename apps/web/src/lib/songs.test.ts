import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deleteJob, deleteTab, ProblemError } from "./api";
import { deleteSongMessage } from "./songs";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const p = (status: number, code: string) => new ProblemError({ status, code, title: code, detail: "d" });

beforeEach(() => vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000"));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("deleting a song", () => {
  it("sends DELETE to the job or the tab", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await deleteJob("j 1");
    await deleteTab("t1");
    const calls = fetchMock.mock.calls.map((c) => [String(c[0]), (c[1] as RequestInit).method]);
    expect(calls[0][0]).toMatch(/\/v1\/jobs\/j%201$/);
    expect(calls[1][0]).toMatch(/\/v1\/tabs\/t1$/);
    expect(calls.map((c) => c[1])).toEqual(["DELETE", "DELETE"]);
  });

  it("treats an already deleted song (404) as deleted", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => json(404, { code: "not_found", detail: "x" })));
    await expect(deleteJob("j1")).resolves.toBeUndefined();
    await expect(deleteTab("t1")).resolves.toBeUndefined();
  });

  it("rethrows other problems", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => json(409, { code: "job_running", detail: "x" })));
    await expect(deleteJob("j1")).rejects.toBeInstanceOf(ProblemError);
  });

  it("explains why a song could not be deleted", () => {
    expect(deleteSongMessage(p(409, "job_running"))).toMatch(/a decorrer/);
    expect(deleteSongMessage(p(503, "storage_unavailable"))).toMatch(/Tente de novo/);
    expect(deleteSongMessage(p(401, "unauthenticated"))).toMatch(/Inicie sessão/);
    expect(deleteSongMessage(new Error("x"))).toBe("Não foi possível apagar a música.");
  });
});
