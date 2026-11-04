export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

/** Same aliases the API accepts (services/api audio_types.py). */
export const ACCEPTED_TYPES = [
  "audio/mpeg",
  "audio/mp3",
  "audio/wav",
  "audio/x-wav",
  "audio/wave",
  "audio/vnd.wave",
  "audio/flac",
  "audio/x-flac",
  "audio/ogg",
] as const;

const BY_EXTENSION: Record<string, string> = {
  mp3: "audio/mpeg",
  wav: "audio/wav",
  flac: "audio/flac",
  ogg: "audio/ogg",
};

export interface FileLike {
  type: string;
  size: number;
  name?: string;
}

/** MIME type to declare: the browser's, or one inferred from the extension when it gives none. */
export function declaredType(file: { type: string; name?: string }): string {
  if (file.type) return file.type;
  const ext = file.name?.split(".").pop()?.toLowerCase() ?? "";
  return BY_EXTENSION[ext] ?? "";
}

/** Client-side pre-check only; the server is authoritative. Returns a pt-PT message or null. */
export function checkFile(file: FileLike): string | null {
  if (!(ACCEPTED_TYPES as readonly string[]).includes(declaredType(file))) {
    return "Formato não suportado. Use MP3, WAV, FLAC ou OGG.";
  }
  if (file.size <= 0) return "O ficheiro está vazio.";
  if (file.size > MAX_UPLOAD_BYTES) return "O ficheiro excede o limite de 50 MiB.";
  return null;
}
