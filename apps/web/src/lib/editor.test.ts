import { describe, expect, it } from "vitest";
import {
  alternatives,
  canRedo,
  canUndo,
  clampSelection,
  createHistory,
  deleteNote,
  moveToString,
  nextNote,
  noteAbove,
  noteBelow,
  noteName,
  parseScore,
  pitchOf,
  playableStrings,
  previousNote,
  pushHistory,
  redo,
  setFret,
  typedFret,
  undo,
  type Score,
  type Selection,
} from "./editor";

const TUNING = [64, 59, 55, 50, 45, 40];

function mk(bars: Array<Array<Array<[number, number, boolean?]>>>): Score {
  return {
    schema_version: 2,
    tempo_bpm: 90,
    time_signature: [4, 4],
    tuning: TUNING,
    bars: bars.map((beats) => ({
      beats: beats.map((notes) => ({
        duration: 8,
        dots: 0,
        tuplet: null,
        notes: notes.map(([string, fret, tie]) => ({ string, fret, tie: tie ?? false })),
      })),
    })),
  };
}

const sel = (bar: number, beat: number, string: number): Selection => ({ bar, beat, string });
const frozen = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

describe("pitch and names", () => {
  it("computes pitch from tuning", () => {
    const s = mk([[[[1, 0]]]]);
    expect(pitchOf(s, 1, 0)).toBe(64);
    expect(pitchOf(s, 6, 3)).toBe(43);
  });
  it("names notes in pt-PT with MIDI 60 = Dó4", () => {
    expect(noteName(60)).toBe("Dó4");
    expect(noteName(64)).toBe("Mi4");
    expect(noteName(40)).toBe("Mi2");
    expect(noteName(61)).toBe("Dó#4");
    expect(noteName(69)).toBe("Lá4");
    expect(noteName(71)).toBe("Si4");
    expect(noteName(52)).toBe("Mi3");
  });
});

describe("alternatives", () => {
  it("lists other playable strings, excluding strings used in the beat", () => {
    // B3 (59): string 2 fret 0 ; also string 3 fret 4, string 4 fret 9, string 5 fret 14, string 6 fret 19
    const s = mk([[[[2, 0], [4, 0]]]]);
    const alts = alternatives(s, sel(0, 0, 2));
    expect(alts).toEqual([
      { string: 3, fret: 4 },
      { string: 5, fret: 14 },
      { string: 6, fret: 19 },
    ]);
    expect(playableStrings(s, sel(0, 0, 2))).toEqual([2, 3, 5, 6]);
  });
  it("excludes strings where the fret would be out of range", () => {
    const s = mk([[[[6, 0]]]]); // E2: only string 6 (fret 0) .. string 5 needs fret -5
    expect(alternatives(s, sel(0, 0, 6))).toEqual([]);
    const high = mk([[[[1, 24]]]]); // E6 playable only on string 1
    expect(alternatives(high, sel(0, 0, 1))).toEqual([]);
  });
  it("returns [] for a missing note", () => {
    expect(alternatives(mk([[[[1, 0]]]]), sel(0, 0, 3))).toEqual([]);
  });
});

describe("setFret", () => {
  it("changes the fret without mutating the input", () => {
    const s = mk([[[[2, 3]]]]);
    const before = frozen(s);
    const e = setFret(s, sel(0, 0, 2), 5)!;
    expect(e.score.bars[0].beats[0].notes[0].fret).toBe(5);
    expect(e.selection).toEqual(sel(0, 0, 2));
    expect(s).toEqual(before);
  });
  it("rejects invalid frets and no-ops", () => {
    const s = mk([[[[2, 3]]]]);
    expect(setFret(s, sel(0, 0, 2), 25)).toBeNull();
    expect(setFret(s, sel(0, 0, 2), -1)).toBeNull();
    expect(setFret(s, sel(0, 0, 2), 1.5)).toBeNull();
    expect(setFret(s, sel(0, 0, 2), 3)).toBeNull();
    expect(setFret(s, sel(0, 0, 4), 3)).toBeNull();
  });
  it("updates the whole tie chain, also across the barline", () => {
    const s = mk([
      [[[1, 5]], [[1, 5, true]]],
      [[[1, 5, true]], [[1, 5, true]], [[1, 7]]],
    ]);
    const e = setFret(s, sel(0, 0, 1), 8)!;
    const frets = e.score.bars.flatMap((b) => b.beats.map((bt) => bt.notes[0].fret));
    expect(frets).toEqual([8, 8, 8, 8, 7]);
    expect(e.score.bars[1].beats[0].notes[0].tie).toBe(true);
  });
  it("editing a tied continuation edits the chain origin and keeps selection", () => {
    const s = mk([[[[1, 5]], [[1, 5, true]], [[1, 5, true]]]]);
    const e = setFret(s, sel(0, 2, 1), 2)!;
    expect(e.score.bars[0].beats.map((b) => b.notes[0].fret)).toEqual([2, 2, 2]);
    expect(e.selection).toEqual(sel(0, 2, 1));
  });
  it("does not touch another string's tie chain", () => {
    const s = mk([[[[1, 5], [2, 3]], [[1, 5, true], [2, 3, true]]]]);
    const e = setFret(s, sel(0, 0, 1), 6)!;
    expect(e.score.bars[0].beats[1].notes).toEqual([
      { string: 1, fret: 6, tie: true },
      { string: 2, fret: 3, tie: true },
    ]);
  });
});

describe("moveToString", () => {
  it("keeps pitch and changes string/fret", () => {
    const s = mk([[[[2, 0]]]]); // B3
    const e = moveToString(s, sel(0, 0, 2), 3)!;
    expect(e.score.bars[0].beats[0].notes).toEqual([{ string: 3, fret: 4, tie: false }]);
    expect(e.selection).toEqual(sel(0, 0, 3));
    expect(pitchOf(e.score, 3, 4)).toBe(59);
  });
  it("rejects used or unplayable strings", () => {
    const s = mk([[[[2, 0], [3, 4]]]]);
    expect(moveToString(s, sel(0, 0, 2), 3)).toBeNull();
    expect(moveToString(mk([[[[6, 0]]]]), sel(0, 0, 6), 5)).toBeNull();
    expect(moveToString(s, sel(0, 0, 2), 2)).toBeNull();
    expect(moveToString(s, sel(0, 0, 2), 7)).toBeNull();
  });
  it("moves the whole tie chain and keeps ties valid", () => {
    const s = mk([[[[2, 0]], [[2, 0, true]]], [[[2, 0, true]]]]);
    const e = moveToString(s, sel(1, 0, 2), 3)!;
    for (const [b, i] of [[0, 0], [0, 1], [1, 0]]) {
      expect(e.score.bars[b].beats[i].notes).toEqual([
        { string: 3, fret: 4, tie: i + b > 0 },
      ]);
    }
    expect(e.selection).toEqual(sel(1, 0, 3));
  });
  it("rejects the move when the target string is used in any chain beat", () => {
    const s = mk([[[[2, 0]], [[2, 0, true], [3, 4]]]]);
    expect(moveToString(s, sel(0, 0, 2), 3)).toBeNull();
    expect(alternatives(s, sel(0, 0, 2)).map((a) => a.string)).not.toContain(3);
  });
  it("does not mutate the input", () => {
    const s = mk([[[[2, 0]]]]);
    const before = frozen(s);
    moveToString(s, sel(0, 0, 2), 3);
    expect(s).toEqual(before);
  });
});

describe("deleteNote", () => {
  it("removes a note, leaving a rest when it was the last", () => {
    const s = mk([[[[1, 0]], [[2, 1]]]]);
    const e = deleteNote(s, sel(0, 0, 1))!;
    expect(e.score.bars[0].beats[0].notes).toEqual([]);
    expect(e.selection).toBeNull();
    expect(s.bars[0].beats[0].notes).toHaveLength(1);
  });
  it("selects a neighbour in the same beat after deleting a chord note", () => {
    const s = mk([[[[1, 0], [2, 1], [3, 0]]]]);
    const e = deleteNote(s, sel(0, 0, 2))!;
    expect(e.score.bars[0].beats[0].notes.map((n) => n.string)).toEqual([1, 3]);
    expect(e.selection).toEqual(sel(0, 0, 3));
  });
  it("deletes the whole tie chain, even when selecting a continuation", () => {
    const s = mk([[[[1, 5], [2, 0]], [[1, 5, true]]], [[[1, 5, true]], [[1, 7]]]]);
    const e = deleteNote(s, sel(1, 0, 1))!;
    expect(e.score.bars[0].beats[0].notes).toEqual([{ string: 2, fret: 0, tie: false }]);
    expect(e.score.bars[0].beats[1].notes).toEqual([]);
    expect(e.score.bars[1].beats[0].notes).toEqual([]);
    expect(e.score.bars[1].beats[1].notes).toEqual([{ string: 1, fret: 7, tie: false }]);
  });
  it("returns null for a missing note", () => {
    expect(deleteNote(mk([[[[1, 0]]]]), sel(0, 0, 2))).toBeNull();
  });
});

describe("navigation", () => {
  const s = mk([
    [[[1, 0], [3, 2]], [], [[3, 5]]],
    [[[6, 0]]],
  ]);
  it("moves to the next beat with notes, nearest string, across bars", () => {
    expect(nextNote(s, sel(0, 0, 3))).toEqual(sel(0, 2, 3));
    expect(nextNote(s, sel(0, 0, 1))).toEqual(sel(0, 2, 3));
    expect(nextNote(s, sel(0, 2, 3))).toEqual(sel(1, 0, 6));
    expect(nextNote(s, sel(1, 0, 6))).toBeNull();
  });
  it("moves to the previous beat with notes", () => {
    expect(previousNote(s, sel(1, 0, 6))).toEqual(sel(0, 2, 3));
    expect(previousNote(s, sel(0, 2, 3))).toEqual(sel(0, 0, 3));
    expect(previousNote(s, sel(0, 0, 1))).toBeNull();
  });
  it("moves within a chord", () => {
    expect(noteBelow(s, sel(0, 0, 1))).toEqual(sel(0, 0, 3));
    expect(noteBelow(s, sel(0, 0, 3))).toBeNull();
    expect(noteAbove(s, sel(0, 0, 3))).toEqual(sel(0, 0, 1));
    expect(noteAbove(s, sel(0, 0, 1))).toBeNull();
  });
  it("clamps a stale selection", () => {
    expect(clampSelection(s, sel(0, 0, 3))).toEqual(sel(0, 0, 3));
    expect(clampSelection(s, sel(0, 0, 2))).toEqual(sel(0, 0, 3));
    expect(clampSelection(s, sel(0, 1, 2))).toBeNull();
    expect(clampSelection(s, sel(9, 0, 2))).toBeNull();
    expect(clampSelection(s, null)).toBeNull();
  });
});

describe("history", () => {
  it("undoes and redoes immutably", () => {
    const h0 = createHistory("a");
    const h1 = pushHistory(h0, "b");
    const h2 = pushHistory(h1, "c");
    expect(canUndo(h2)).toBe(true);
    const u = undo(h2);
    expect(u.present).toBe("b");
    expect(redo(u).present).toBe("c");
    expect(h2.present).toBe("c");
    expect(canRedo(u)).toBe(true);
    expect(canUndo(h0)).toBe(false);
    expect(undo(h0)).toBe(h0);
    expect(redo(h2)).toBe(h2);
  });
  it("clears redo on a new push and caps the stack", () => {
    let h = createHistory(0);
    for (let i = 1; i <= 150; i++) h = pushHistory(h, i);
    expect(h.past.length).toBe(100);
    let back = h;
    while (canUndo(back)) back = undo(back);
    expect(back.present).toBe(50);
    const forked = pushHistory(undo(h), -1);
    expect(canRedo(forked)).toBe(false);
  });
  it("merge replaces the present without growing the past", () => {
    const h = pushHistory(pushHistory(createHistory("a"), "b"), "c", true);
    expect(h.past).toEqual(["a"]);
    expect(h.present).toBe("c");
  });
});

describe("typedFret", () => {
  it("applies the first digit immediately and combines a second within the window", () => {
    const a = typedFret(null, 1, 1000);
    expect(a.fret).toBe(1);
    const b = typedFret(a.buffer, 2, 1500);
    expect(b.fret).toBe(12);
    expect(b.merge).toBe(true);
  });
  it("starts over after the window", () => {
    const a = typedFret(null, 1, 1000);
    const b = typedFret(a.buffer, 2, 1800);
    expect(b.fret).toBe(2);
    expect(b.merge).toBe(false);
  });
  it("ignores a combination above 24", () => {
    const a = typedFret(null, 3, 0);
    const b = typedFret(a.buffer, 0, 100);
    expect(b.fret).toBeNull();
    const c = typedFret(null, 2, 0);
    expect(typedFret(c.buffer, 5, 100).fret).toBeNull();
    expect(typedFret(c.buffer, 4, 100).fret).toBe(24);
  });
});

describe("parseScore", () => {
  it("accepts a valid score and rejects garbage", () => {
    expect(parseScore(mk([[[[1, 0]]]])).bars).toHaveLength(1);
    expect(() => parseScore(null)).toThrow();
    expect(() => parseScore({ bars: [] })).toThrow();
    expect(() => parseScore({ ...mk([[[[1, 0]]]]), tuning: [1, 2] })).toThrow();
  });
});
