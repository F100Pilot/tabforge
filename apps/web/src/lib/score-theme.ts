export type ScoreTheme = "dark" | "light";
export const SCORE_THEME_KEY = "tabforge.scoreTheme";

export const SCORE_COLORS = {
  dark: {
    background: "#14171C",
    mainGlyphColor: "#E6E8EB",
    secondaryGlyphColor: "#9AA1AC",
    staffLineColor: "#4A505B",
    barSeparatorColor: "#8A919C",
    barNumberColor: "#F2B544",
    scoreInfoColor: "#C9CED6",
  },
  light: {
    background: "#FAFAF7",
    mainGlyphColor: "#1B1D21",
    secondaryGlyphColor: "#6B7079",
    staffLineColor: "#A3A39B",
    barSeparatorColor: "#4A4E55",
    barNumberColor: "#9A6A12",
    scoreInfoColor: "#1B1D21",
  },
} as const;

export function parseScoreTheme(v: unknown): ScoreTheme {
  return v === "light" ? "light" : "dark";
}

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): StorageLike | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function loadScoreTheme(storage: StorageLike | null = defaultStorage()): ScoreTheme {
  try {
    return parseScoreTheme(storage?.getItem(SCORE_THEME_KEY));
  } catch {
    return "dark";
  }
}

export function saveScoreTheme(theme: ScoreTheme, storage: StorageLike | null = defaultStorage()): void {
  try {
    storage?.setItem(SCORE_THEME_KEY, theme);
  } catch {
    /* storage unavailable: the choice just won't persist */
  }
}
