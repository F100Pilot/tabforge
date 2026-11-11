import { isUnauthenticated, ProblemError } from "./api";

/** Why DELETE /v1/jobs/{id} or /v1/tabs/{id} failed, for the person deleting the song. */
export function deleteSongMessage(err: unknown): string {
  if (isUnauthenticated(err)) return "Inicie sessão para continuar.";
  if (err instanceof ProblemError) {
    switch (err.code) {
      case "job_running":
        return "A transcrição ainda está a decorrer. Apague quando terminar.";
      case "storage_unavailable":
        return "Não foi possível apagar o áudio. Tente de novo.";
    }
  }
  return "Não foi possível apagar a música.";
}
