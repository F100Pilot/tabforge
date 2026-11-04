/**
 * US-05 export in the browser with alphaTab (ADR-0007): Guitar Pro 7 (.gp) and standard MIDI
 * (.mid), both built from the server-generated alphaTex of the current revision.
 */
import type * as AlphaTab from "@coderline/alphatab";

type AlphaTabModule = typeof AlphaTab;
export type ExportFormat = "gp" | "midi";

export interface ExportedFile {
  bytes: Uint8Array;
  filename: string;
  mime: string;
}

const EXTENSION: Record<ExportFormat, string> = { gp: "gp", midi: "mid" };
const MIME: Record<ExportFormat, string> = { gp: "application/octet-stream", midi: "audio/midi" };
const MAX_NAME = 80;
const REVOKE_AFTER_MS = 30_000;
// Reserved on Windows/macOS/Linux, plus control characters.
const FORBIDDEN = /[\\/:*?"<>|\u0000-\u001f\u007f]/g;

export function exportFileName(title: string, format: ExportFormat): string {
  const cleaned = title.replace(FORBIDDEN, "").replace(/\s+/g, " ").trim().replace(/^[.\s]+|[.\s]+$/g, "");
  const base = cleaned.slice(0, MAX_NAME) || "tablatura";
  return `${base}.${EXTENSION[format]}`;
}

/** Throws if the alphaTex does not parse (alphaTab's AlphaTexError). */
export function exportScore(at: AlphaTabModule, alphatex: string, title: string, format: ExportFormat): ExportedFile {
  const settings = new at.Settings();
  const score = at.importer.ScoreLoader.loadAlphaTex(alphatex, settings);
  score.title = title;
  let bytes: Uint8Array;
  if (format === "gp") {
    bytes = new at.exporter.Gp7Exporter().export(score, settings);
  } else {
    const midi = new at.midi.MidiFile();
    midi.format = at.midi.MidiFileFormat.MultiTrack;
    new at.midi.MidiFileGenerator(score, settings, new at.midi.AlphaSynthMidiFileHandler(midi, true)).generate();
    bytes = midi.toBinary();
  }
  return { bytes, filename: exportFileName(title, format), mime: MIME[format] };
}

/** Hands the file to the browser as a download. */
export function saveFile(file: ExportedFile): void {
  const url = URL.createObjectURL(new Blob([file.bytes as BlobPart], { type: file.mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename;
  document.body.append(link);
  link.click();
  link.remove();
  // Some browsers start the download asynchronously; keep the URL alive for a while.
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
}
