import { describe, expect, it } from "vitest";
import { matchingTrackIndex, scoreTracks, warningSummary, withTrack } from "./tracks";

const TUNING = [64, 59, 55, 50, 45, 40];
const bar = (fret: number) => ({ beats: [{ duration: 4, notes: [{ string: 1, fret }] }] });
const W = { bar: 1, code: "pitch_out_of_range", pitch: 20 };

const v2 = { schema_version: 2, tempo_bpm: 90, time_signature: [4, 4], tuning: TUNING, bars: [bar(0)], warnings: [W] };
const v3 = {
  schema_version: 3,
  tempo_bpm: 90,
  time_signature: [4, 4],
  tracks: [
    { name: "Lead", tuning: TUNING, bars: [bar(1)], warnings: [] },
    { name: "Rhythm", tuning: [62, 57, 53, 48, 43, 38], bars: [bar(2)], warnings: [W, W] },
  ],
};

describe("scoreTracks", () => {
  it("sees a v2 score as one track named Guitarra", () => {
    const t = scoreTracks(v2);
    expect(t).toHaveLength(1);
    expect(t[0]).toMatchObject({ name: "Guitarra", tuning: TUNING, warnings: [W] });
    expect(t[0].bars).toBe(v2.bars);
  });

  it("lists the tracks of a v3 score in order", () => {
    const t = scoreTracks(v3);
    expect(t.map((x) => x.name)).toEqual(["Lead", "Rhythm"]);
    expect(t[1].tuning).toEqual([62, 57, 53, 48, 43, 38]);
    expect(t[1].warnings).toHaveLength(2);
  });

  it("is empty for anything that is not a score, and names unnamed tracks", () => {
    expect(scoreTracks(null)).toEqual([]);
    expect(scoreTracks("x")).toEqual([]);
    expect(scoreTracks({})).toEqual([{ name: "Guitarra", tuning: [], bars: [], warnings: [] }]);
    expect(scoreTracks({ tracks: [{ tuning: TUNING, bars: [] }] })[0].name).toBe("Pista 1");
  });
});

describe("withTrack", () => {
  it("keeps v2 as v2 and does not mutate", () => {
    const next = withTrack(v2, 0, { tuning: TUNING, bars: [bar(5)] });
    expect(next).not.toBe(v2);
    expect(next.schema_version).toBe(2);
    expect("tracks" in next).toBe(false);
    expect(next.bars[0].beats[0].notes[0].fret).toBe(5);
    expect(next.warnings).toEqual([W]);
    expect(v2.bars[0].beats[0].notes[0].fret).toBe(0);
  });

  it("replaces only the chosen track of a v3 score", () => {
    const next = withTrack(v3, 1, { tuning: TUNING, bars: [bar(9)] });
    expect(next.schema_version).toBe(3);
    expect(next.tracks[0]).toBe(v3.tracks[0]);
    expect(next.tracks[1].name).toBe("Rhythm");
    expect(next.tracks[1].bars[0].beats[0].notes[0].fret).toBe(9);
    expect(next.tracks[1].warnings).toHaveLength(2);
    expect(v3.tracks[1].bars[0].beats[0].notes[0].fret).toBe(2);
  });

  it("ignores an out-of-range index", () => {
    expect(withTrack(v3, 5, { tuning: TUNING, bars: [] })).toBe(v3);
    expect(withTrack(v2, 1, { tuning: TUNING, bars: [] })).toBe(v2);
  });
});

describe("warningSummary", () => {
  it("sums warnings and lists tracks that have some", () => {
    expect(warningSummary(scoreTracks(v3))).toEqual({ total: 2, perTrack: [{ name: "Rhythm", count: 2 }] });
    expect(warningSummary(scoreTracks(v2)).total).toBe(1);
  });
});

describe("matchingTrackIndex", () => {
  const cands = [
    { index: 0, name: "Drums" },
    { index: 2, name: "Lead Guitar" },
    { index: 3, name: "RHYTHM gtr" },
  ];
  it("matches by shared word, case-insensitively", () => {
    expect(matchingTrackIndex("Lead", cands)).toBe(2);
    expect(matchingTrackIndex("Rhythm", cands)).toBe(3);
  });
  it("returns null when nothing matches", () => {
    expect(matchingTrackIndex("Guitarra", cands)).toBeNull();
    expect(matchingTrackIndex("Solo", cands)).toBeNull();
  });
});
