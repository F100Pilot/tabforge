/** Presentation helpers for the ADR-0009 comparison card (pure, pt-PT). */
import { ProblemError, type BarComparison, type Comparison } from "./api";

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
    if (err.status === 404) return "A tablatura já não existe.";
    if (err.status === 401) return "A sessão expirou. Entre outra vez.";
    return err.message;
  }
  return "Não foi possível comparar a tablatura.";
}
