/**
 * ADR-0009: reads the "right" tab (Guitar Pro .gp3-.gp7) with alphaTab in the browser and turns
 * one guitar track into the plain note list the API stores and compares.
 */
import type * as AlphaTab from "@coderline/alphatab";

type AlphaTabModule = typeof AlphaTab;

export const REFERENCE_STRINGS = 6;
export const MAX_REFERENCE_NOTES = 20000;
export const MAX_REFERENCE_FILE_BYTES = 20 * 1024 * 1024;
export const REFERENCE_EXTENSIONS = [".gp", ".gp3", ".gp4", ".gp5", ".gpx"] as const;
/** alphaTab's MidiUtils.QuarterTime (not exported in the typings): ticks in a quarter note. */
export const TICKS_PER_QUARTER = 960;

export interface ReferenceTrack {
  index: number;
  name: string;
  strings: number;
}

export interface ReferenceNote {
  onset: number;
  pitch: number;
  string: number;
  fret: number;
  bar: number;
}

/** Tracks that can be compared: stringed (not percussion/piano) with exactly six strings. */
export function readReferenceTracks(at: AlphaTabModule, bytes: Uint8Array): { score: AlphaTab.model.Score; tracks: ReferenceTrack[] } {
  const score = at.importer.ScoreLoader.loadScoreFromBytes(bytes, new at.Settings());
  const tracks: ReferenceTrack[] = [];
  score.tracks.forEach((track, index) => {
    const staff = track.staves[0];
    if (!staff || !staff.isStringed || staff.tuning.length !== REFERENCE_STRINGS) return;
    tracks.push({ index, name: track.name.trim() || `Pista ${index + 1}`, strings: staff.tuning.length });
  });
  return { score, tracks };
}

/**
 * Notes of the track's first staff in time order, without repeat expansion. Skips rests, tie
 * destinations (the sustain of an earlier note) and dead notes. `string` is 1 = highest string.
 */
export function referenceNotes(score: AlphaTab.model.Score, trackIndex: number): ReferenceNote[] {
  const staff = score.tracks[trackIndex]?.staves[0];
  if (!staff) return [];
  const stringCount = staff.tuning.length;
  const notes: ReferenceNote[] = [];
  for (const bar of staff.bars) {
    for (const voice of bar.voices) {
      for (const beat of voice.beats) {
        if (beat.isRest) continue;
        for (const note of beat.notes) {
          if (note.isTieDestination || note.isDead || !note.isStringed) continue;
          notes.push({
            onset: beat.absolutePlaybackStart / TICKS_PER_QUARTER,
            pitch: note.realValueWithoutHarmonic,
            // alphaTab: 1 = lowest string; ours: 1 = highest.
            string: stringCount + 1 - note.string,
            fret: note.fret,
            bar: bar.index + 1,
          });
        }
      }
    }
  }
  notes.sort((a, b) => a.onset - b.onset || a.pitch - b.pitch);
  return notes;
}

export function hasReferenceExtension(name: string): boolean {
  const lower = name.toLowerCase();
  return REFERENCE_EXTENSIONS.some((ext) => lower.endsWith(ext));
}
