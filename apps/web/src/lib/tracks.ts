/**
 * ADR-0010: Score v1/v2 (one implicit track "Guitarra") and v3 (`tracks[]`) seen as a list of
 * tracks, plus immutable replacement of one track that keeps the score's original shape.
 */
import type { ScoreBar } from "./editor";

export const DEFAULT_TRACK_NAME = "Guitarra";
export const MAX_TRACKS = 4;

export interface TrackWarning {
  bar: number;
  code: string;
  pitch: number;
}

export interface ScoreTrack {
  name: string;
  tuning: number[];
  bars: ScoreBar[];
  warnings: TrackWarning[];
}

/** What the editing functions need from a track (a v2 score fits too). */
export interface TrackBody {
  tuning: number[];
  bars: ScoreBar[];
}

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);

function readWarnings(v: unknown): TrackWarning[] {
  if (!Array.isArray(v)) return [];
  return v.filter(
    (w): w is TrackWarning =>
      isRec(w) && typeof w.bar === "number" && typeof w.code === "string" && typeof w.pitch === "number",
  );
}

function readTrack(r: Rec, fallbackName: string): ScoreTrack {
  const name = typeof r.name === "string" && r.name.trim() !== "" ? r.name.trim() : fallbackName;
  return {
    name,
    tuning: Array.isArray(r.tuning) ? (r.tuning as number[]) : [],
    bars: Array.isArray(r.bars) ? (r.bars as ScoreBar[]) : [],
    warnings: readWarnings(r.warnings),
  };
}

/** Tracks of a v1/v2/v3 score (a v1/v2 object is one track, even if incomplete); `[]` for a non-object. */
export function scoreTracks(score: unknown): ScoreTrack[] {
  if (!isRec(score)) return [];
  if (Array.isArray(score.tracks)) {
    return score.tracks
      .filter(isRec)
      .map((t, i) => readTrack(t, `Pista ${i + 1}`));
  }
  return [readTrack(score, DEFAULT_TRACK_NAME)];
}

/**
 * New score where track `index` has the given tuning/bars (and warnings when given). The shape is
 * kept: a v2 score stays v2, a v3 score stays v3. Inputs are never mutated.
 */
export function withTrack<T>(
  score: T,
  index: number,
  track: TrackBody & { warnings?: TrackWarning[] },
): T {
  if (!isRec(score)) return score;
  const patch = (old: Rec): Rec => ({
    ...old,
    tuning: track.tuning,
    bars: track.bars,
    ...(track.warnings !== undefined ? { warnings: track.warnings } : {}),
  });
  if (Array.isArray(score.tracks)) {
    if (index < 0 || index >= score.tracks.length) return score;
    const tracks = score.tracks.map((t: unknown, i: number) => (i === index && isRec(t) ? patch(t) : t));
    return { ...score, tracks } as T;
  }
  if (index !== 0) return score;
  return patch(score) as T;
}

/** Total of omitted-note warnings and the per-track counts that have any. */
export function warningSummary(tracks: Array<Pick<ScoreTrack, "name" | "warnings">>): { total: number; perTrack: Array<{ name: string; count: number }> } {
  const perTrack = tracks.map((t) => ({ name: t.name, count: t.warnings.length })).filter((t) => t.count > 0);
  return { total: perTrack.reduce((n, t) => n + t.count, 0), perTrack };
}

/** Index of the reference track whose name shares the word of `name` ("Lead"/"Rhythm"), or null. */
export function matchingTrackIndex(name: string, candidates: Array<{ index: number; name: string }>): number | null {
  const words = name.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((w) => w.length >= 3);
  if (words.length === 0) return null;
  const hit = candidates.find((c) => {
    const lower = c.name.toLowerCase();
    return words.some((w) => lower.includes(w));
  });
  return hit ? hit.index : null;
}
