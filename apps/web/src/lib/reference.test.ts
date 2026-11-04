import * as at from "@coderline/alphatab";
import { describe, expect, it } from "vitest";
import { hasReferenceExtension, readReferenceTracks, referenceNotes } from "./reference";

function toGp(tex: string): Uint8Array {
  const settings = new at.Settings();
  const score = at.importer.ScoreLoader.loadAlphaTex(tex, settings);
  return new at.exporter.Gp7Exporter().export(score, settings);
}

// Bar 1: dotted quarter (fret 3 on string 6), eighth (open string 1), half (fret 5 on string 3).
// Bar 2: eighth rest, eighth (fret 5 on string 3), tie destination, dead note.
const TEX = String.raw`\title "ref" \tempo 100 \tuning (E4 B3 G3 D3 A2 E2) \ts (4 4)
3.6.4 {d} 0.1.8 5.3.2 | r.8 5.3.8 -.3.8 x.2.8 |`;

describe("readReferenceTracks", () => {
  it("lists the six-string tracks and ignores others", () => {
    const tex = String.raw`\track "Guitarra" \staff{tabs} \tuning (E4 B3 G3 D3 A2 E2)
0.1.1 |
\track "Baixo" \staff{tabs} \tuning (G2 D2 A1 E1)
0.1.1 |`;
    const { tracks } = readReferenceTracks(at, toGp(tex));
    expect(tracks).toEqual([{ index: 0, name: "Guitarra", strings: 6 }]);
  });

  it("throws for a file that is not Guitar Pro", () => {
    expect(() => readReferenceTracks(at, new Uint8Array([1, 2, 3, 4]))).toThrow();
  });
});

describe("referenceNotes", () => {
  const { score } = readReferenceTracks(at, toGp(TEX));
  const notes = referenceNotes(score, 0);

  it("measures onsets in quarter notes, including a dotted note and a rest", () => {
    expect(notes.map((n) => n.onset)).toEqual([0, 1.5, 2, 4.5]);
  });

  it("numbers strings from the highest and bars from 1", () => {
    expect(notes.map((n) => [n.string, n.fret, n.bar])).toEqual([
      [6, 3, 1],
      [1, 0, 1],
      [3, 5, 1],
      [3, 5, 2],
    ]);
  });

  it("returns real MIDI pitches for standard tuning", () => {
    expect(notes.map((n) => n.pitch)).toEqual([43, 64, 60, 60]);
  });

  it("skips tie destinations and dead notes", () => {
    expect(notes).toHaveLength(4);
  });

  it("includes the capo in the pitch but keeps the written fret", () => {
    const capoScore = at.importer.ScoreLoader.loadAlphaTex(TEX, new at.Settings());
    capoScore.tracks[0].staves[0].capo = 2;
    const capoNotes = referenceNotes(capoScore, 0);
    expect(capoNotes.map((n) => n.pitch)).toEqual([45, 66, 62, 62]);
    expect(capoNotes[0].fret).toBe(3);
  });

  it("returns nothing for an unknown track", () => {
    expect(referenceNotes(score, 5)).toEqual([]);
  });
});

describe("hasReferenceExtension", () => {
  it("accepts Guitar Pro extensions only", () => {
    expect(hasReferenceExtension("Song.GP5")).toBe(true);
    expect(hasReferenceExtension("a.gpx")).toBe(true);
    expect(hasReferenceExtension("a.mid")).toBe(false);
  });
});
