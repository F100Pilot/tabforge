/**
 * Pure editing logic on one track ({tuning, bars}) of a Score v2/v3. Every function returns new
 * values and never mutates its inputs; the caller puts the result back with `withTrack`.
 */
import { scoreTracks, type TrackBody } from "./tracks";

export type { TrackBody };

export interface ScoreNote {
  string: number;
  fret: number;
  tie?: boolean;
}
export interface ScoreBeat {
  duration: number;
  dots?: number;
  tuplet?: number | null;
  notes: ScoreNote[];
}
export interface ScoreBar {
  beats: ScoreBeat[];
}
export interface Score {
  schema_version: number;
  tempo_bpm: number;
  time_signature: [number, number];
  tuning: number[];
  bars: ScoreBar[];
  warnings?: Array<{ bar: number; code: string; pitch: number }>;
}

/** `string` uses the score numbering: 1 = highest string. */
export interface Selection {
  bar: number;
  beat: number;
  string: number;
}
export interface Edit {
  /** The edited track (same extra fields as the input track). */
  score: TrackBody;
  selection: Selection | null;
}

export const MAX_FRET = 24;
export const HISTORY_LIMIT = 100;
export const TYPE_WINDOW_MS = 700;

const NAMES = ["Dó", "Dó#", "Ré", "Ré#", "Mi", "Fá", "Fá#", "Sol", "Sol#", "Lá", "Lá#", "Si"];

const invalidScore = () => new Error("Partitura inválida.");

function checkTrack(r: { tuning: unknown; bars: unknown }): void {
  if (
    !Array.isArray(r.tuning) ||
    r.tuning.length !== 6 ||
    !r.tuning.every((n) => Number.isInteger(n)) ||
    !Array.isArray(r.bars)
  ) {
    throw invalidScore();
  }
  for (const bar of r.bars as unknown[]) {
    const b = bar as { beats?: unknown } | null;
    if (!b || !Array.isArray(b.beats)) throw invalidScore();
    for (const beat of b.beats as unknown[]) {
      const bt = beat as { notes?: unknown } | null;
      if (!bt || !Array.isArray(bt.notes)) throw invalidScore();
      for (const n of bt.notes as unknown[]) {
        const nn = n as { string?: unknown; fret?: unknown } | null;
        if (!nn || !Number.isInteger(nn.string) || !Number.isInteger(nn.fret)) throw invalidScore();
      }
    }
  }
}

/** A whole score document, v1/v2 (one track) or v3 (`tracks`). */
export type ScoreDoc = Record<string, unknown>;

/** Validates every track of a v1/v2/v3 score; throws "Partitura inválida." */
export function parseScoreDoc(v: unknown): ScoreDoc {
  if (typeof v !== "object" || v === null || Array.isArray(v)) throw invalidScore();
  const tracks = scoreTracks(v);
  if (tracks.length === 0) throw invalidScore();
  const raw = (v as { tracks?: unknown }).tracks;
  if (Array.isArray(raw) && raw.length !== tracks.length) throw invalidScore();
  tracks.forEach(checkTrack);
  return v as ScoreDoc;
}

export function parseScore(v: unknown): Score {
  if (typeof v !== "object" || v === null) throw invalidScore();
  checkTrack(v as { tuning: unknown; bars: unknown });
  return v as Score;
}

export function pitchOf(score: TrackBody, string: number, fret: number): number {
  return score.tuning[string - 1] + fret;
}

export function noteName(pitch: number): string {
  return `${NAMES[((pitch % 12) + 12) % 12]}${Math.floor(pitch / 12) - 1}`;
}

function beatAt(score: TrackBody, bar: number, beat: number): ScoreBeat | null {
  return score.bars[bar]?.beats[beat] ?? null;
}

export function findNote(score: TrackBody, s: Selection): ScoreNote | null {
  return beatAt(score, s.bar, s.beat)?.notes.find((n) => n.string === s.string) ?? null;
}

/** Previous beat position (crossing barlines), or null at the start. */
function prevPos(score: TrackBody, bar: number, beat: number): [number, number] | null {
  if (beat > 0) return [bar, beat - 1];
  for (let b = bar - 1; b >= 0; b--) {
    const n = score.bars[b].beats.length;
    if (n > 0) return [b, n - 1];
  }
  return null;
}

function nextPos(score: TrackBody, bar: number, beat: number): [number, number] | null {
  if (beat + 1 < (score.bars[bar]?.beats.length ?? 0)) return [bar, beat + 1];
  for (let b = bar + 1; b < score.bars.length; b++) {
    if (score.bars[b].beats.length > 0) return [b, 0];
  }
  return null;
}

/** The notes of a tie chain on one string, origin first. Null when the note does not exist. */
export function chainOf(score: TrackBody, s: Selection): Selection[] | null {
  if (!findNote(score, s)) return null;
  let origin: Selection = { bar: s.bar, beat: s.beat, string: s.string };
  for (;;) {
    const note = findNote(score, origin)!;
    if (!note.tie) break;
    const p = prevPos(score, origin.bar, origin.beat);
    if (!p) break;
    const prev = { bar: p[0], beat: p[1], string: s.string };
    if (!findNote(score, prev)) break;
    origin = prev;
  }
  const chain: Selection[] = [origin];
  let cur = origin;
  for (;;) {
    const p = nextPos(score, cur.bar, cur.beat);
    if (!p) break;
    const next = { bar: p[0], beat: p[1], string: s.string };
    const note = findNote(score, next);
    if (!note || !note.tie) break;
    chain.push(next);
    cur = next;
  }
  return chain;
}

function rebuild(
  score: TrackBody,
  chain: Selection[],
  fn: (notes: ScoreNote[], at: Selection) => ScoreNote[],
): TrackBody {
  const byBar = new Map<number, Map<number, Selection>>();
  for (const c of chain) {
    if (!byBar.has(c.bar)) byBar.set(c.bar, new Map());
    byBar.get(c.bar)!.set(c.beat, c);
  }
  return {
    ...score,
    bars: score.bars.map((bar, bi) => {
      const beats = byBar.get(bi);
      if (!beats) return bar;
      return {
        ...bar,
        beats: bar.beats.map((beat, ti) => {
          const at = beats.get(ti);
          return at ? { ...beat, notes: fn(beat.notes, at) } : beat;
        }),
      };
    }),
  };
}

/** Strings where the chain's pitch is playable (0..24) and no other note of any chain beat uses them. Includes the current string. */
export function playableStrings(score: TrackBody, s: Selection): number[] {
  const chain = chainOf(score, s);
  if (!chain) return [];
  const origin = chain[0];
  const pitch = pitchOf(score, s.string, findNote(score, origin)!.fret);
  const out: number[] = [];
  for (let str = 1; str <= score.tuning.length; str++) {
    const fret = pitch - score.tuning[str - 1];
    if (fret < 0 || fret > MAX_FRET) continue;
    if (str !== s.string) {
      const used = chain.some((c) => beatAt(score, c.bar, c.beat)!.notes.some((n) => n.string === str));
      if (used) continue;
    }
    out.push(str);
  }
  return out;
}

export function alternatives(score: TrackBody, s: Selection): Array<{ string: number; fret: number }> {
  const chain = chainOf(score, s);
  if (!chain) return [];
  const pitch = pitchOf(score, s.string, findNote(score, chain[0])!.fret);
  return playableStrings(score, s)
    .filter((str) => str !== s.string)
    .map((str) => ({ string: str, fret: pitch - score.tuning[str - 1] }));
}

export function setFret(score: TrackBody, s: Selection, fret: number): Edit | null {
  if (!Number.isInteger(fret) || fret < 0 || fret > MAX_FRET) return null;
  const chain = chainOf(score, s);
  if (!chain) return null;
  if (findNote(score, chain[0])!.fret === fret) return null;
  const next = rebuild(score, chain, (notes, at) =>
    notes.map((n) => (n.string === at.string ? { ...n, fret } : n)),
  );
  return { score: next, selection: s };
}

export function moveToString(score: TrackBody, s: Selection, target: number): Edit | null {
  if (target === s.string || !playableStrings(score, s).includes(target)) return null;
  const chain = chainOf(score, s)!;
  const fret = pitchOf(score, s.string, findNote(score, chain[0])!.fret) - score.tuning[target - 1];
  const next = rebuild(score, chain, (notes, at) =>
    notes
      .map((n) => (n.string === at.string ? { ...n, string: target, fret } : n))
      .sort((a, b) => a.string - b.string),
  );
  return { score: next, selection: { ...s, string: target } };
}

export function deleteNote(score: TrackBody, s: Selection): Edit | null {
  const chain = chainOf(score, s);
  if (!chain) return null;
  const next = rebuild(score, chain, (notes, at) => notes.filter((n) => n.string !== at.string));
  // Prefer the nearest remaining note of the beat the user was on.
  return { score: next, selection: clampSelection(next, { ...s }) };
}

function sortedStrings(score: TrackBody, bar: number, beat: number): number[] {
  return (beatAt(score, bar, beat)?.notes ?? []).map((n) => n.string).sort((a, b) => a - b);
}

function nearest(strings: number[], target: number): number {
  return strings.reduce((best, s) => (Math.abs(s - target) <= Math.abs(best - target) ? s : best), strings[0]);
}

export function clampSelection(score: TrackBody, s: Selection | null): Selection | null {
  if (!s) return null;
  const strings = sortedStrings(score, s.bar, s.beat);
  if (strings.length === 0) return null;
  return { ...s, string: strings.includes(s.string) ? s.string : nearest(strings, s.string) };
}

export function firstNote(score: TrackBody): Selection | null {
  for (let b = 0; b < score.bars.length; b++) {
    for (let t = 0; t < score.bars[b].beats.length; t++) {
      const strings = sortedStrings(score, b, t);
      if (strings.length) return { bar: b, beat: t, string: strings[0] };
    }
  }
  return null;
}

function step(score: TrackBody, s: Selection, dir: 1 | -1): Selection | null {
  let pos: [number, number] | null = [s.bar, s.beat];
  for (;;) {
    pos = dir === 1 ? nextPos(score, pos[0], pos[1]) : prevPos(score, pos[0], pos[1]);
    if (!pos) return null;
    const strings = sortedStrings(score, pos[0], pos[1]);
    if (strings.length) return { bar: pos[0], beat: pos[1], string: nearest(strings, s.string) };
  }
}

export const nextNote = (score: TrackBody, s: Selection) => step(score, s, 1);
export const previousNote = (score: TrackBody, s: Selection) => step(score, s, -1);

/** Up on the tab = a lower string number. */
export function noteAbove(score: TrackBody, s: Selection): Selection | null {
  const above = sortedStrings(score, s.bar, s.beat).filter((x) => x < s.string);
  return above.length ? { ...s, string: above[above.length - 1] } : null;
}

export function noteBelow(score: TrackBody, s: Selection): Selection | null {
  const below = sortedStrings(score, s.bar, s.beat).filter((x) => x > s.string);
  return below.length ? { ...s, string: below[0] } : null;
}

/* History */

export interface History<T> {
  past: T[];
  present: T;
  future: T[];
}

export const createHistory = <T>(present: T): History<T> => ({ past: [], present, future: [] });
export const canUndo = <T>(h: History<T>) => h.past.length > 0;
export const canRedo = <T>(h: History<T>) => h.future.length > 0;

/** `merge` replaces the present instead of adding an undo step (e.g. the second digit of "12"). */
export function pushHistory<T>(h: History<T>, value: T, merge = false): History<T> {
  if (merge) return { past: h.past, present: value, future: [] };
  return { past: [...h.past, h.present].slice(-HISTORY_LIMIT), present: value, future: [] };
}

export function undo<T>(h: History<T>): History<T> {
  if (!canUndo(h)) return h;
  return { past: h.past.slice(0, -1), present: h.past[h.past.length - 1], future: [h.present, ...h.future] };
}

export function redo<T>(h: History<T>): History<T> {
  if (!canRedo(h)) return h;
  return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1) };
}

/* Typed frets */

export interface TypeBuffer {
  digit: number;
  at: number;
}

/** First digit applies at once; a second within the window makes a two-digit fret (ignored above 24). */
export function typedFret(
  buffer: TypeBuffer | null,
  digit: number,
  now: number,
): { fret: number | null; merge: boolean; buffer: TypeBuffer | null } {
  if (buffer && now - buffer.at <= TYPE_WINDOW_MS) {
    const fret = buffer.digit * 10 + digit;
    if (fret > MAX_FRET) return { fret: null, merge: false, buffer: null };
    return { fret, merge: true, buffer: null };
  }
  return { fret: digit, merge: false, buffer: { digit, at: now } };
}
