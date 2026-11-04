import type { JobStage, JobStatus, JobSummary } from "./api";

export const STEPS: { stage: JobStage; label: string; hint: string }[] = [
  { stage: "normalizing", label: "Recebido", hint: "Formato verificado" },
  { stage: "separating", label: "Isolar guitarra", hint: "Separação da guitarra" },
  { stage: "transcribing", label: "Transcrever notas", hint: "A detetar as notas" },
  { stage: "arranging", label: "Cordas e trastes", hint: "A escolher as posições" },
];

export type StepState = "done" | "current" | "pending" | "skipped" | "failed";

/** State of each stepper step. `sourceKind` null means unknown. */
export function stepStates(
  status: JobStatus,
  stage: JobStage | null,
  sourceKind: JobSummary["source_kind"] | null,
): StepState[] {
  const current = stage ? STEPS.findIndex((s) => s.stage === stage) : 0;
  return STEPS.map((_, i) => {
    if (i === 1 && sourceKind === "guitar_stem") return "skipped";
    if (status === "done") return "done";
    if (i < current) return "done";
    if (i === current) return status === "failed" ? "failed" : "current";
    return "pending";
  });
}

export function stepHint(i: number, state: StepState, sourceKind: JobSummary["source_kind"] | null): string {
  if (i === 1 && state === "skipped") return "Saltado · já é só guitarra";
  if (i === 1 && sourceKind === null) return "—";
  return STEPS[i].hint;
}

export function errorMessage(code: string | null): string {
  switch (code) {
    case "audio_too_long":
      return "A gravação tem mais de 10 minutos. Corte-a e volte a carregar.";
    case "audio_unreadable":
      return "Não foi possível ler o ficheiro de áudio.";
    case "max_attempts_exceeded":
      return "Falhou várias vezes. Tente mais tarde.";
    default:
      return "A transcrição falhou. Tente novamente com outro ficheiro.";
  }
}

export type StatusTone = "ok" | "info" | "error";

export function statusView(status: JobStatus): { label: string; tone: StatusTone } {
  switch (status) {
    case "done":
      return { label: "Pronta", tone: "ok" };
    case "failed":
      return { label: "Falhou", tone: "error" };
    case "queued":
      return { label: "Em fila", tone: "info" };
    default:
      return { label: "A processar", tone: "info" };
  }
}

export function jobTitle(j: Pick<JobSummary, "status" | "tab_title">): string {
  if (j.tab_title) return j.tab_title;
  return j.status === "done" ? "Sem título" : "A processar…";
}

export function jobHref(j: Pick<JobSummary, "id" | "status" | "tab_id">): string {
  return j.status === "done" && j.tab_id
    ? `/tabs/${encodeURIComponent(j.tab_id)}`
    : `/jobs/${encodeURIComponent(j.id)}`;
}
