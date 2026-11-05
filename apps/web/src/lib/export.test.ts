import * as at from "@coderline/alphatab";
import { describe, expect, it } from "vitest";
import { exportFileName, exportScore } from "./export";

// Shape of the server's alphaTex (tabforge_score.to_alphatex): tuplets, dots, ties and rests.
const TEX = String.raw`\title "real" \tempo 89 \tuning (E4 B3 G3 D3 A2 E2)
\ts (4 4) r.8{d} (4.5 2.2).16 3.3.4 {tu 3} 0.1.8 {tu 3} 1.1.8 {tu 3} -.1.4 | 5.6.2 r.2 |`;

function frets(score: at.model.Score): string[] {
  return score.tracks[0].staves[0].bars.flatMap((bar) =>
    bar.voices[0].beats.flatMap((beat) => beat.notes.map((n) => `${n.string}:${n.fret}${n.isTieDestination ? "~" : ""}`)),
  );
}

describe("exportFileName", () => {
  it("keeps the title readable and adds the extension", () => {
    expect(exportFileName("Transcrição 2026-11-04", "gp")).toBe("Transcrição 2026-11-04.gp");
    expect(exportFileName("Riff", "midi")).toBe("Riff.mid");
  });

  it("removes characters that are not allowed in file names", () => {
    expect(exportFileName('a/b\\c:d*e?f"g<h>i|j\u0000k', "gp")).toBe("abcdefghijk.gp");
  });

  it("falls back to a default name and caps the length", () => {
    expect(exportFileName("  ..  ", "gp")).toBe("tablatura.gp");
    expect(exportFileName("x".repeat(300), "midi")).toBe(`${"x".repeat(80)}.mid`);
  });
});

describe("exportScore", () => {
  it("writes a Guitar Pro 7 file that reads back with the same notes, tempo and title", () => {
    const file = exportScore(at, TEX, "Meu riff", "gp");
    expect(file.filename).toBe("Meu riff.gp");
    expect(String.fromCharCode(file.bytes[0], file.bytes[1])).toBe("PK"); // GP7 is a zip container
    const original = at.importer.ScoreLoader.loadAlphaTex(TEX, new at.Settings());
    const back = at.importer.ScoreLoader.loadScoreFromBytes(file.bytes, new at.Settings());
    expect(frets(back)).toEqual(frets(original));
    expect(back.tempo).toBe(89);
    expect(back.title).toBe("Meu riff");
  });

  it("writes a standard MIDI file with one note-on per sounding note", () => {
    const file = exportScore(at, TEX, "Meu riff", "midi");
    expect(file.filename).toBe("Meu riff.mid");
    expect(file.mime).toBe("audio/midi");
    expect(String.fromCharCode(...file.bytes.slice(0, 4))).toBe("MThd");
    const header = new DataView(file.bytes.buffer, file.bytes.byteOffset, 14);
    expect(header.getUint16(8)).toBe(1); // SMF type 1 (multi-track)
  });

  it("rejects alphaTex that does not parse", () => {
    expect(() => exportScore(at, "\\tuning (", "x", "gp")).toThrow();
  });
});

describe("exportScore with two tracks (ADR-0010)", () => {
  const TEX2 = String.raw`\title "banda" \tempo 100 \ts (4 4)
\track "Lead" \staff {tabs} \tuning (E4 B3 G3 D3 A2 E2)
3.1.4 5.1.4 7.1.4 5.1.4 |
\track "Rhythm" \staff {tabs} \tuning (E4 B3 G3 D3 A2 E2)
(0.6 2.5 2.4).2 (0.6 2.5 2.4).2 |`;

  it("writes a Guitar Pro file that reads back with both tracks", () => {
    const file = exportScore(at, TEX2, "Banda", "gp");
    const back = at.importer.ScoreLoader.loadScoreFromBytes(file.bytes, new at.Settings());
    expect(back.tracks.map((t) => t.name)).toEqual(["Lead", "Rhythm"]);
  });

  it("writes a MIDI file with a track per guitar", () => {
    const file = exportScore(at, TEX2, "Banda", "midi");
    expect(file.bytes.length).toBeGreaterThan(40);
  });
});
