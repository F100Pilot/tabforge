import { describe, expect, it } from "vitest";
import type { BarComparison, Comparison, Difference } from "./api";
import { alignmentNotes, barDescription, barRatio, correctionsSummary, describeDifference, applyResultMessage, conflictMessage, formatDecimal, formatPercent, referenceProblemMessage } from "./comparison-view";
import { ProblemError } from "./api";

const base: Comparison = {
  revision_id: "r",
  shift_quarters: 0,
  scale: 1,
  matched: 0,
  ai_notes: 0,
  reference_notes: 0,
  recall: 0,
  precision: 0,
  f1: 0,
  position_accuracy: null,
  onset_error: null,
  bars: [],
  differences: { counts: { position: 0, missing: 0, extra: 0, timing: 0 }, items: [], truncated: false },
  tab_tuning_name: "E standard",
  reference_tuning_name: "E standard",
};

describe("formatters", () => {
  it("formats percentages and decimals in pt-PT", () => {
    expect(formatPercent(0.667)).toBe("67 %");
    expect(formatPercent(1)).toBe("100 %");
    expect(formatPercent(null)).toBe("—");
    expect(formatDecimal(0.125)).toBe("0,1");
    expect(formatDecimal(2)).toBe("2");
    expect(formatDecimal(1.5)).toBe("1,5");
  });
});

describe("alignmentNotes", () => {
  it("is empty when aligned at the same tempo", () => expect(alignmentNotes(base)).toEqual([]));
  it("reports the shift in beats (quarter notes)", () => {
    expect(alignmentNotes({ ...base, shift_quarters: 4 })).toEqual(["A tab certa começa 4 tempos depois."]);
    expect(alignmentNotes({ ...base, shift_quarters: 1 })).toEqual(["A tab certa começa 1 tempo depois."]);
    expect(alignmentNotes({ ...base, shift_quarters: -2.5 })).toEqual(["A tab certa começa 2,5 tempos antes."]);
  });
  it("reports a doubled or halved tempo", () => {
    expect(alignmentNotes({ ...base, scale: 0.5 })).toEqual(["Andamento detetado ao dobro."]);
    expect(alignmentNotes({ ...base, scale: 2 })).toEqual(["Andamento detetado a metade."]);
  });
  it("reports a correct tab in another tuning", () => {
    expect(alignmentNotes({ ...base, reference_tuning_name: "B standard" })).toEqual([
      "A tab certa está em B standard e esta em E standard: as posições só coincidem depois de aplicar as correções, que mudam a afinação.",
    ]);
    expect(alignmentNotes({ ...base, tab_tuning_name: null, reference_tuning_name: null })).toEqual([]);
  });
});

describe("bars", () => {
  const bar = (matched: number, reference_notes: number): BarComparison => ({ bar: 3, reference_notes, matched, positions_ok: 1 });
  it("computes the matched ratio, null for empty bars", () => {
    expect(barRatio(bar(2, 4))).toBe(0.5);
    expect(barRatio(bar(0, 0))).toBeNull();
  });
  it("describes a bar in words", () => {
    expect(barDescription(bar(2, 4))).toBe("Compasso 3: 2 de 4 notas encontradas, 1 na posição certa.");
    expect(barDescription(bar(0, 0))).toBe("Compasso 3: sem notas na tab certa.");
  });
});

describe("referenceProblemMessage", () => {
  const p = (status: number) => new ProblemError({ status, code: "c", title: "", detail: "d" });
  it("maps statuses to friendly messages", () => {
    expect(referenceProblemMessage(p(413))).toMatch(/demasiado grande/);
    expect(referenceProblemMessage(p(422))).toMatch(/não é válida/);
    expect(referenceProblemMessage(p(404))).toMatch(/já não existe/);
    expect(referenceProblemMessage(new Error("x"))).toBe("Não foi possível comparar a tablatura.");
  });
  it("tells an outdated API (no such route) apart from a deleted tab", () => {
    const route = new ProblemError({ status: 404, code: "not_found", title: "", detail: "Not Found" });
    expect(referenceProblemMessage(route)).toMatch(/start\.bat/);
    const ref = new ProblemError({ status: 404, code: "reference_not_found", title: "", detail: "x" });
    expect(referenceProblemMessage(ref)).toMatch(/não tem tab certa/);
  });
});

const d = (over: Partial<Difference>): Difference => ({
  kind: "position", bar: 12, onset: 1, pitch: 64,
  ai: { string: 2, fret: 5, bar: 11, beat: 0 }, ref: { string: 1, fret: 0 }, onset_error: null, ...over,
});

describe("describeDifference", () => {
  it("position", () => {
    expect(describeDifference(d({}))).toBe("Compasso 12 · Mi4 — IA: corda 2, traste 5 → certa: corda 1, traste 0");
  });
  it("missing", () => {
    expect(describeDifference(d({ kind: "missing", bar: 7, pitch: 55, ai: null }))).toBe("Compasso 7 · Sol3 — em falta na IA");
  });
  it("extra", () => {
    expect(describeDifference(d({ kind: "extra", bar: 9, pitch: 69, ref: null }))).toBe("Compasso 9 · Lá4 — nota a mais na IA");
  });
  it("timing", () => {
    expect(describeDifference(d({ kind: "timing", bar: 3, pitch: 62, onset_error: 0.2 }))).toBe(
      "Compasso 3 · Ré4 — ataque desviado ≈ 0,2 tempo",
    );
    expect(describeDifference(d({ kind: "timing", onset_error: null }))).toContain("ataque desviado");
  });
  it("position without detail falls back gracefully", () => {
    expect(describeDifference(d({ ai: null, ref: null }))).toBe("Compasso 12 · Mi4 — posição errada");
  });
});

describe("correctionsSummary", () => {
  it("lists non-zero counts, pluralised", () => {
    expect(correctionsSummary({ position: 12, missing: 30, extra: 8, timing: 5 })).toBe(
      "12 posições erradas · 30 notas em falta · 8 a mais · 5 ritmo",
    );
    expect(correctionsSummary({ position: 1, missing: 1, extra: 0, timing: 0 })).toBe("1 posição errada · 1 nota em falta");
  });
  it("says nothing was detected", () => {
    expect(correctionsSummary({ position: 0, missing: 0, extra: 0, timing: 0 })).toBe("Nenhuma diferença detetada.");
  });
});

describe("apply messages", () => {
  it("result", () => {
    expect(applyResultMessage(5, 2)).toBe("Corrigidas 5 posições (2 ignoradas: corda ocupada)");
    expect(applyResultMessage(1, 1)).toBe("Corrigida 1 posição (1 ignorada: corda ocupada)");
    expect(applyResultMessage(3, 0)).toBe("Corrigidas 3 posições");
    expect(applyResultMessage(0, 4)).toBe("Nenhuma posição corrigida (4 ignoradas: corda ocupada)");
    expect(applyResultMessage(380, 0, "B standard")).toBe("Corrigidas 380 posições. Afinação mudada para B standard.");
  });
  it("conflict", () => {
    expect(conflictMessage(new ProblemError({ status: 409, code: "revision_conflict", title: "t", detail: "d" }))).toBe(
      "A tab mudou noutro lado; recarregue.",
    );
    expect(conflictMessage(new Error("x"))).toBeNull();
  });
});
