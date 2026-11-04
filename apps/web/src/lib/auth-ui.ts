import { ProblemError } from "./api";

/** Extracts `token` from a URL fragment such as `#token=abc`; null when absent/empty. */
export function tokenFromHash(hash: string): string | null {
  const params = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
  const token = params.get("token")?.trim();
  return token ? token : null;
}

/** Deletion is confirmed by typing the account email (case and surrounding spaces ignored). */
export function emailMatches(typed: string, email: string): boolean {
  return typed.trim().toLowerCase() === email.trim().toLowerCase() && email.trim() !== "";
}

export function magicLinkErrorMessage(err: unknown): string {
  if (err instanceof ProblemError) {
    if (err.status === 422) return "Introduza um endereço de email válido.";
    if (err.status === 429) return "Demasiados pedidos. Aguarde um pouco e tente novamente.";
  }
  return "Não foi possível enviar o link. Tente novamente.";
}

export function deleteAccountErrorMessage(err: unknown): string {
  if (err instanceof ProblemError && err.status === 503) {
    return "O armazenamento está indisponível neste momento. Nada foi eliminado; tente novamente dentro de instantes.";
  }
  return "Não foi possível eliminar a conta. Tente novamente.";
}

/** "invalid" = link expired, used or unknown; "failed" = anything else. */
export function verifyErrorKind(err: unknown): "invalid" | "failed" {
  return err instanceof ProblemError && err.status === 400 && err.code === "invalid_token" ? "invalid" : "failed";
}
