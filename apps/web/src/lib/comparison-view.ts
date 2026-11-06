/** Presentation helpers for the ADR-0009 comparison card (pure, pt-PT). */
import { ProblemError, type BarComparison, type Comparison, type Difference, type Differences } from "./api";
import { noteName } from "./editor";

export function formatPercent(v: number | null): string {
  return v === null ? "—" : `${Math.round(v * 100)} %`;
}

/** One decimal at most, comma separator ("0,1", "2", "2,5"). */
export function formatDecimal(v: number): string {
  return (Math.round(v * 10) / 10).toString().replace(".", ",");
}

export function alignmentNotes(c: Comparison): string[] {
  const notes: string[] = [];
  if (c.shift_quarters !== 0) {
    const n = Math.abs(c.shift_quarters);
    const unit = Math.round(n * 10) / 10 === 1 ? "tempo" : "tempos";
    notes.push(`A tab certa começa ${formatDecimal(n)} ${unit} ${c.shift_quarters > 0 ? "depois" : "antes"}.`);
  }
  // compare(): reference ≈ scale × transcription + shift. scale 0.5 means the transcription
  // counted twice as many beats, i.e. it locked onto double tempo.
  if (c.scale === 0.5) notes.push("Andamento detetado ao dobro.");
  else if (c.scale === 2) notes.push("Andamento detetado a metade.");
  const tab = c.tab_tuning_name;
  const ref = c.reference_tuning_name;
  if (tab && ref && tab !== ref) {
    notes.push(
      `A tab certa está em ${ref} e esta em ${tab}: as posições só coincidem depois de aplicar as correções, que mudam a afinação.`,
    );
  }
  return notes;
}

/** Fraction of the reference bar's notes that were found; null for a bar without notes. */
export function barRatio(b: BarComparison): number | null {
  return b.reference_notes > 0 ? b.matched / b.reference_notes : null;
}

export function barDescription(b: BarComparison): string {
  if (b.reference_notes === 0) return `Compasso ${b.bar}: sem notas na tab certa.`;
  return `Compasso ${b.bar}: ${b.matched} de ${b.reference_notes} notas encontradas, ${b.positions_ok} na posição certa.`;
}

export function referenceProblemMessage(err: unknown): string {
  if (err instanceof ProblemError) {
    if (err.status === 413) return "A tab certa é demasiado grande. Escolha outra pista ou um ficheiro mais curto.";
    if (err.status === 422) return "A tab certa não é válida (sem notas ou notas fora do limite).";
    // Starlette's own 404 for an unknown route: the API predates the comparison (desktop
    // started from an older checkout), not a deleted tab.
    if (err.status === 404 && err.message === "Not Found") {
      return "A aplicação está desatualizada. Feche o TabForge e corra o start.bat outra vez.";
    }
    if (err.code === "reference_not_found") return "Esta pista ainda não tem tab certa guardada.";
    if (err.status === 404) return "A tablatura já não existe.";
    if (err.status === 401) return "A sessão expirou. Entre outra vez.";
    return err.message;
  }
  return "Não foi possível comparar a tablatura.";
}

const PT_NOTES = ["Dó", "Dó#", "Ré", "Ré#", "Mi", "Fá", "Fá#", "Sol", "Sol#", "Lá", "Lá#", "Si"];

/** Solfège name with octave ("Mi4" for MIDI 64). */
export function ptNoteName(pitch: number): string {
  const idx = ((pitch % 12) + 12) % 12;
  // Reuse the editor's octave convention so both views agree.
  const octave = noteName(pitch).replace(/^\D+/, "");
  return `${PT_NOTES[idx]}${octave}`;
}

/** One line for the list of detected corrections (pt-PT). */
export function describeDifference(d: Difference): string {
  const head = `Compasso ${d.bar} · ${ptNoteName(d.pitch)} — `;
  switch (d.kind) {
    case "position":
      return d.ai && d.ref
        ? `${head}IA: corda ${d.ai.string}, traste ${d.ai.fret} → certa: corda ${d.ref.string}, traste ${d.ref.fret}`
        : `${head}posição errada`;
    case "missing":
      return `${head}em falta na IA`;
    case "extra":
      return `${head}nota a mais na IA`;
    case "timing":
      return d.onset_error === null
        ? `${head}ataque desviado`
        : `${head}ataque desviado ≈ ${formatDecimal(d.onset_error)} tempo`;
  }
}

/** "12 posições erradas · 30 notas em falta · 8 a mais · 5 ritmo"; zero counts are left out. */
export function correctionsSummary(c: Differences["counts"]): string {
  const parts: string[] = [];
  if (c.position > 0) parts.push(`${c.position} ${c.position === 1 ? "posição errada" : "posições erradas"}`);
  if (c.missing > 0) parts.push(`${c.missing} ${c.missing === 1 ? "nota em falta" : "notas em falta"}`);
  if (c.extra > 0) parts.push(`${c.extra} a mais`);
  if (c.timing > 0) parts.push(`${c.timing} ritmo`);
  return parts.length > 0 ? parts.join(" · ") : "Nenhuma diferença detetada.";
}

export function applyResultMessage(applied: number, skipped: number, retunedTo: string | null = null): string {
  const skippedText = skipped > 0 ? ` (${skipped} ${skipped === 1 ? "ignorada" : "ignoradas"}: corda ocupada)` : "";
  const tuningText = retunedTo ? `. Afinação mudada para ${retunedTo}.` : "";
  if (applied === 0) return `Nenhuma posição corrigida${skippedText}${tuningText}`;
  return `${applied === 1 ? "Corrigida 1 posição" : `Corrigidas ${applied} posições`}${skippedText}${tuningText}`;
}

/** Message for a 409 `revision_conflict`; null for any other error. */
export function conflictMessage(err: unknown): string | null {
  return err instanceof ProblemError && err.status === 409 ? "A tab mudou noutro lado; recarregue." : null;
}
