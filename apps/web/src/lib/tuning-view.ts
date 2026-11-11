/** Presentation helpers for the ADR-0011 "Aprendizagem" card (pure, pt-PT). */
import { ProblemError, type Tuning, type TuningStatus } from "./api";
import { formatPercent } from "./comparison-view";

export const POLL_INTERVAL_MS = 3000;
export const POLL_MAX_MS = 120_000;

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export function statusLine(t: Tuning): string {
  switch (t.status) {
    case "none":
      return `Ainda não aprendeu: compare pelo menos ${plural(t.min_tabs, "tab", "tabs")} com a tab certa (${t.min_notes} notas).`;
    case "stale":
      return "A aprender com as suas tabs…";
    case "ready":
      return `Aprendeu com ${plural(t.tabs, "tab", "tabs")} (${plural(t.notes, "nota", "notas")}).`;
    case "insufficient":
      return `Dados insuficientes: ${plural(t.tabs, "tab", "tabs")}, ${plural(t.notes, "nota", "notas")}; precisa de ${plural(t.min_tabs, "tab", "tabs")} e ${t.min_notes} notas.`;
  }
}

export function accuracyLine(t: Tuning): string | null {
  if (t.status !== "ready" || t.default_accuracy === null || t.tuned_accuracy === null) return null;
  return `Posições certas: ${formatPercent(t.default_accuracy)} → ${formatPercent(t.tuned_accuracy)} (medido em notas que não serviram para aprender)`;
}

export function inUseLine(t: Tuning): string | null {
  if (t.status !== "ready") return null;
  return t.in_use
    ? "Em uso nas próximas transcrições."
    : "Os pesos aprendidos não melhoraram; continua com os pesos de origem.";
}

const WEIGHT_LABELS = [
  ["span", "Abertura da mão"],
  ["height", "Altura no braço"],
  ["move", "Movimento"],
  ["open_move", "Movimento com corda solta"],
] as const;

export function weightRows(t: Tuning): Array<{ key: string; label: string; value: string }> {
  const w = t.weights;
  if (!w) return [];
  return WEIGHT_LABELS.map(([key, label]) => ({ key, label, value: (Math.round(w[key] * 100) / 100).toString().replace(".", ",") }));
}

export function shouldPoll(status: TuningStatus, elapsedMs: number): boolean {
  return status === "stale" && elapsedMs < POLL_MAX_MS;
}

export function tuningProblemMessage(err: unknown): string {
  if (err instanceof ProblemError) return err.message;
  return "Não foi possível contactar o servidor.";
}
