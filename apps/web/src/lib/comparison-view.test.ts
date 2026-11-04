import { describe, expect, it } from "vitest";
import type { BarComparison, Comparison } from "./api";
import { alignmentNotes, barDescription, barRatio, formatDecimal, formatPercent, referenceProblemMessage } from "./comparison-view";
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
});
