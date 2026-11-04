/** "mm:ss" from milliseconds. */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** "m:ss" for the player clock. */
export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Relative time in pt-PT ("há 5 min"); `now` injectable for tests. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const sec = Math.max(0, Math.round((now - t) / 1000));
  if (sec < 60) return "agora mesmo";
  const min = Math.floor(sec / 60);
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `há ${h} h`;
  const d = Math.floor(h / 24);
  if (d < 30) return d === 1 ? "há 1 dia" : `há ${d} dias`;
  return new Date(t).toLocaleDateString("pt-PT");
}

export function formatDate(iso: string): string {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? "" : new Date(t).toLocaleDateString("pt-PT", { timeZone: "UTC" });
}

/** Tuning for display; the API shape is loose, so accept a string or an array of strings. */
export function formatTuning(tuning: unknown): string | null {
  if (typeof tuning === "string") return tuning.trim() || null;
  if (Array.isArray(tuning) && tuning.length > 0 && tuning.every((t) => typeof t === "string")) {
    return tuning.join(" ");
  }
  return null;
}
