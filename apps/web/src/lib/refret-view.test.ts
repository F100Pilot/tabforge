import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseTab, ProblemError, refretTab } from "./api";
import { refretMessage, refretProblemMessage, sourceLabel } from "./refret-view";

const p = (status: number, code: string, detail = "d") => new ProblemError({ status, code, title: code, detail });

describe("refret view (ADR-0016)", () => {
  it("names where a revision came from", () => {
    expect(sourceLabel("ai")).toBe("Gerada por IA");
    expect(sourceLabel("user")).toBe("Editada por si");
    expect(sourceLabel("learned")).toBe("Posições aprendidas");
  });

  it("says how many notes moved", () => {
    expect(refretMessage(0)).toBe("As posições já seguem o que aprendeu; nada mudou.");
    expect(refretMessage(1)).toMatch(/^1 nota mudou de posição\./);
    expect(refretMessage(12)).toMatch(/^12 notas mudaram de posição\./);
  });

  it("explains failures", () => {
    expect(refretProblemMessage(p(409, "no_learned_weights"))).toMatch(/Aprendizagem/);
    expect(refretProblemMessage(p(409, "revision_conflict"))).toMatch(/recarregue/);
    expect(refretProblemMessage(p(401, "unauthenticated"))).toMatch(/sessão expirou/);
    expect(refretProblemMessage(p(500, "boom", "Erro X"))).toBe("Erro X");
    expect(refretProblemMessage(new Error("x"))).toBe("Não foi possível refazer as posições.");
  });
});

describe("refretTab", () => {
  const tab = {
    id: "t1",
    title: "Riff",
    tuning: "E standard",
    visibility: "private",
    created_at: "2026-11-11",
    revision: { id: "r2", source: "learned", created_at: "2026-11-11", score: {} },
    alphatex: "\\title x",
  };
  beforeEach(() => vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000"));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("reads tabs whose revision has the learned source", () => {
    expect(parseTab(tab).revision.source).toBe("learned");
  });

  it("posts the base revision and returns the new tab", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ tab, changed: 3 }), { status: 201, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const r = await refretTab("t1", "r1");
    expect(r.changed).toBe(3);
    expect(r.tab.revision.id).toBe("r2");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/v1\/tabs\/t1\/refret$/);
    expect(JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))).toEqual({ base_revision_id: "r1" });
  });
});
