/** Presentation helpers for "Refazer as posições com o que aprendi" (ADR-0016; pure, pt-PT). */
import { isUnauthenticated, ProblemError, type RevisionSource } from "./api";

export function sourceLabel(source: RevisionSource): string {
  switch (source) {
    case "ai":
      return "Gerada por IA";
    case "user":
      return "Editada por si";
    case "learned":
      return "Posições aprendidas";
  }
}

export function refretMessage(changed: number): string {
  if (changed === 0) return "As posições já seguem o que aprendeu; nada mudou.";
  const moved = changed === 1 ? "1 nota mudou de posição." : `${changed} notas mudaram de posição.`;
  return `${moved} A versão anterior fica no histórico do editor.`;
}

export function refretProblemMessage(err: unknown): string {
  if (isUnauthenticated(err)) return "A sessão expirou. Entre outra vez.";
  if (err instanceof ProblemError) {
    if (err.code === "no_learned_weights") return "Ainda não há nada aprendido em uso. Veja a página Aprendizagem.";
    if (err.code === "revision_conflict") return "A tab mudou noutro lado; recarregue.";
    return err.message;
  }
  return "Não foi possível refazer as posições.";
}
