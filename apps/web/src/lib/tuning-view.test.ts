import { describe, expect, it } from "vitest";
import type { Tuning } from "./api";
import {
  POLL_INTERVAL_MS,
  POLL_MAX_MS,
  accuracyLine,
  shouldPoll,
  statusLine,
  tuningProblemMessage,
  inUseLine,
  weightRows,
} from "./tuning-view";
import { ProblemError } from "./api";

const base: Tuning = {
  status: "none",
  tabs: 0,
  notes: 0,
  default_accuracy: null,
  tuned_accuracy: null,
  in_use: false,
  weights: null,
  updated_at: null,
  min_notes: 200,
  min_tabs: 2,
};

describe("statusLine", () => {
  it("none", () =>
    expect(statusLine(base)).toBe("Ainda não aprendeu: compare pelo menos 2 tabs com a tab certa (200 notas)."));
  it("stale", () => expect(statusLine({ ...base, status: "stale" })).toBe("A aprender com as suas tabs…"));
  it("ready", () =>
    expect(statusLine({ ...base, status: "ready", tabs: 3, notes: 640 })).toBe("Aprendeu com 3 tabs (640 notas)."));
  it("ready singular", () =>
    expect(statusLine({ ...base, status: "ready", tabs: 1, notes: 1 })).toBe("Aprendeu com 1 tab (1 nota)."));
  it("insufficient", () =>
    expect(statusLine({ ...base, status: "insufficient", tabs: 1, notes: 80 })).toBe(
      "Dados insuficientes: 1 tab, 80 notas; precisa de 2 tabs e 200 notas.",
    ));
  it("uses the server minimums", () =>
    expect(statusLine({ ...base, min_tabs: 3, min_notes: 300 })).toContain("pelo menos 3 tabs"));
});

describe("accuracyLine", () => {
  it("only when ready with both numbers", () => {
    expect(accuracyLine({ ...base, status: "ready", default_accuracy: 0.62, tuned_accuracy: 0.714 })).toBe(
      "Posições certas: 62 % → 71 % (validado tab a tab)",
    );
    expect(accuracyLine({ ...base, status: "ready", default_accuracy: 0.62, tuned_accuracy: null })).toBeNull();
    expect(accuracyLine({ ...base, status: "stale", default_accuracy: 0.62, tuned_accuracy: 0.7 })).toBeNull();
  });
});

describe("inUseLine", () => {
  it("in use", () => expect(inUseLine({ ...base, status: "ready", in_use: true })).toBe("Em uso nas próximas transcrições."));
  it("not in use", () =>
    expect(inUseLine({ ...base, status: "ready", in_use: false })).toBe(
      "Os pesos aprendidos não melhoraram; continua com os pesos de origem.",
    ));
  it("null when not ready", () => expect(inUseLine({ ...base, status: "none" })).toBeNull());
});

describe("weightRows", () => {
  it("lists the four weights in Portuguese", () => {
    const rows = weightRows({ ...base, weights: { span: 1, height: 0.25, move: 2.5, open_move: 0 } });
    expect(rows).toEqual([
      { key: "span", label: "Abertura da mão", value: "1" },
      { key: "height", label: "Altura no braço", value: "0,25" },
      { key: "move", label: "Movimento", value: "2,5" },
      { key: "open_move", label: "Movimento com corda solta", value: "0" },
    ]);
  });
  it("empty without weights", () => expect(weightRows(base)).toEqual([]));
});

describe("shouldPoll / constants", () => {
  it("polls only while stale and before the limit", () => {
    expect(shouldPoll("stale", 0)).toBe(true);
    expect(shouldPoll("stale", POLL_MAX_MS)).toBe(false);
    expect(shouldPoll("ready", 0)).toBe(false);
    expect(POLL_INTERVAL_MS).toBe(3000);
    expect(POLL_MAX_MS).toBe(120_000);
  });
});

describe("tuningProblemMessage", () => {
  it("handles problems and unknowns", () => {
    const p = new ProblemError({ status: 500, code: "x", title: "t", detail: "Falhou." });
    expect(tuningProblemMessage(p)).toBe("Falhou.");
    expect(tuningProblemMessage(new Error("boom"))).toBe("Não foi possível contactar o servidor.");
  });
});
