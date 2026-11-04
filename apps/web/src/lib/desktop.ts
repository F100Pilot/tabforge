/**
 * Desktop build (ADR-0008): one local user, signed in by the launcher with a per-start token.
 * Must reference process.env.NEXT_PUBLIC_TABFORGE_DESKTOP literally so Next inlines it.
 */
export const IS_DESKTOP = process.env.NEXT_PUBLIC_TABFORGE_DESKTOP === "1";

export const DESKTOP_RESTART_MESSAGE = "A sessão local terminou. Feche e volte a abrir o TabForge.";
