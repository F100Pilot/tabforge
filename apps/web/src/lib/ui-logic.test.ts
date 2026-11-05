import { describe, expect, it } from "vitest";
import {
  ResponseShapeError,
  parseJob,
  parseJobList,
  parseTabList,
  readScoreInfo,
} from "./api";
import { formatClock, formatDate, formatDuration, formatTuning, relativeTime } from "./format";
import { errorMessage, jobHref, jobTitle, statusView, stepHint, stepStates } from "./job-view";
import { loadScoreTheme, parseScoreTheme, saveScoreTheme, SCORE_THEME_KEY } from "./score-theme";

const job = {
  id: "j1",
  status: "done",
  stage: null,
  attempts: 1,
  error_code: null,
  tab_id: "t1",
  created_at: "2026-11-04T10:00:00Z",
  updated_at: "2026-11-04T10:00:01Z",
  source_kind: "guitar_stem",
  duration_ms: 83000,
  tab_title: "Exemplo",
};

describe("new endpoint guards", () => {
  it("accepts normalizing stage", () =>
    expect(parseJob({ ...job, status: "running", stage: "normalizing" }).stage).toBe("normalizing"));
  it("parses a job list", () => expect(parseJobList({ items: [job] })[0].tab_title).toBe("Exemplo"));
  it("allows null duration/title", () =>
    expect(parseJobList({ items: [{ ...job, duration_ms: null, tab_title: null }] })).toHaveLength(1));
  it("rejects bad source_kind", () =>
    expect(() => parseJobList({ items: [{ ...job, source_kind: "x" }] })).toThrow(ResponseShapeError));
  it("rejects missing items", () => expect(() => parseJobList({})).toThrow(ResponseShapeError));
  it("parses a tab list", () =>
    expect(
      parseTabList({ items: [{ id: "t", title: "A", tuning: null, visibility: "private", created_at: "x" }] }),
    ).toHaveLength(1));
  it("rejects bad tab list item", () =>
    expect(() => parseTabList({ items: [{ id: 1 }] })).toThrow(ResponseShapeError));
});

describe("readScoreInfo", () => {
  it("reads v2 fields", () => {
    const i = readScoreInfo({
      tempo_bpm: 96,
      time_signature: [3, 4],
      warnings: [{ bar: 1, code: "x", pitch: 30 }, { bad: true }],
    });
    expect(i).toEqual({
      tempo_bpm: 96,
      time_signature: [3, 4],
      warnings: [{ bar: 1, code: "x", pitch: 30 }],
      tracks: [{ name: "Guitarra", tuning: [], warnings: [{ bar: 1, code: "x", pitch: 30 }] }],
    });
  });
  it("reads v3: warnings are summed, tuning and name are per track", () => {
    const w = { bar: 1, code: "x", pitch: 30 };
    const i = readScoreInfo({
      schema_version: 3,
      tempo_bpm: 100,
      time_signature: [4, 4],
      tracks: [
        { name: "Lead", tuning: [64], bars: [], warnings: [w] },
        { name: "Rhythm", tuning: [62], bars: [], warnings: [w, w] },
      ],
    });
    expect(i.tracks.map((t) => t.name)).toEqual(["Lead", "Rhythm"]);
    expect(i.warnings).toHaveLength(3);
  });
  it("degrades on v1 / junk", () => {
    expect(readScoreInfo({ tempo_bpm: "x", time_signature: [0, 4] })).toEqual({
      tempo_bpm: null,
      time_signature: null,
      warnings: [],
      tracks: [{ name: "Guitarra", tuning: [], warnings: [] }],
    });
    expect(readScoreInfo(null).warnings).toEqual([]);
  });
});

describe("format", () => {
  it("duration", () => {
    expect(formatDuration(83000)).toBe("01:23");
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(-5)).toBe("00:00");
  });
  it("clock", () => expect(formatClock(65400)).toBe("1:05"));
  it("relative time", () => {
    const now = Date.parse("2026-11-04T12:00:00Z");
    expect(relativeTime("2026-11-04T11:59:40Z", now)).toBe("agora mesmo");
    expect(relativeTime("2026-11-04T11:55:00Z", now)).toBe("há 5 min");
    expect(relativeTime("2026-11-04T09:00:00Z", now)).toBe("há 3 h");
    expect(relativeTime("2026-11-03T09:00:00Z", now)).toBe("há 1 dia");
    expect(relativeTime("2026-11-01T09:00:00Z", now)).toBe("há 3 dias");
    expect(relativeTime("nope", now)).toBe("");
  });
  it("date", () => expect(formatDate("2026-11-04T10:00:00Z")).toMatch(/2026/));
  it("tuning", () => {
    expect(formatTuning(["E4", "B3"])).toBe("E4 B3");
    expect(formatTuning("Drop D")).toBe("Drop D");
    expect(formatTuning([64, 59])).toBeNull();
    expect(formatTuning(null)).toBeNull();
  });
});

describe("job view", () => {
  it("error messages", () => {
    expect(errorMessage("audio_too_long")).toContain("10 minutos");
    expect(errorMessage("audio_unreadable")).toContain("ler o ficheiro");
    expect(errorMessage("max_attempts_exceeded")).toContain("várias vezes");
    expect(errorMessage("zzz")).toContain("falhou");
    expect(errorMessage(null)).toContain("falhou");
  });
  it("stepper states", () => {
    expect(stepStates("running", "transcribing", "mix")).toEqual(["done", "done", "current", "pending"]);
    expect(stepStates("running", "transcribing", "guitar_stem")).toEqual(["done", "skipped", "current", "pending"]);
    expect(stepStates("queued", null, null)).toEqual(["current", "pending", "pending", "pending"]);
    expect(stepStates("done", "arranging", "mix")).toEqual(["done", "done", "done", "done"]);
    expect(stepStates("failed", "separating", "mix")).toEqual(["done", "failed", "pending", "pending"]);
  });
  it("step hints", () => {
    expect(stepHint(1, "skipped", "guitar_stem")).toBe("Saltado · já é só guitarra");
    expect(stepHint(1, "pending", null)).toBe("—");
    expect(stepHint(0, "done", null)).toBe("Formato verificado");
  });
  it("status/title/href", () => {
    expect(statusView("done")).toEqual({ label: "Pronta", tone: "ok" });
    expect(statusView("queued").label).toBe("Em fila");
    expect(statusView("running").label).toBe("A processar");
    expect(statusView("failed").tone).toBe("error");
    expect(jobTitle({ status: "running", tab_title: null })).toBe("A processar…");
    expect(jobTitle({ status: "done", tab_title: null })).toBe("Sem título");
    expect(jobTitle({ status: "done", tab_title: "X" })).toBe("X");
    expect(jobHref({ id: "j", status: "done", tab_id: "t" })).toBe("/tabs/t");
    expect(jobHref({ id: "j", status: "running", tab_id: null })).toBe("/jobs/j");
  });
});

describe("score theme storage", () => {
  const mem = (init?: string) => {
    const m = new Map<string, string>(init ? [[SCORE_THEME_KEY, init]] : []);
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
  };
  const broken = {
    getItem: () => {
      throw new Error("blocked");
    },
    setItem: () => {
      throw new Error("blocked");
    },
  };
  it("defaults to dark", () => {
    expect(loadScoreTheme(mem())).toBe("dark");
    expect(parseScoreTheme("garbage")).toBe("dark");
    expect(loadScoreTheme(null)).toBe("dark");
  });
  it("round-trips", () => {
    const s = mem();
    saveScoreTheme("light", s);
    expect(loadScoreTheme(s)).toBe("light");
  });
  it("survives throwing storage", () => {
    expect(loadScoreTheme(broken)).toBe("dark");
    expect(() => saveScoreTheme("light", broken)).not.toThrow();
  });
});
