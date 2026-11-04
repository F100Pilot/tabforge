"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { AlphaTabApi } from "@coderline/alphatab";
import { getTab, readScoreInfo, type ScoreInfo, type Tab } from "@/lib/api";
import { formatClock, formatTuning } from "@/lib/format";
import { loadScoreTheme, SCORE_COLORS, saveScoreTheme, type ScoreTheme } from "@/lib/score-theme";

const ASSET_BASE = "/alphatab";

function resourceColors(theme: ScoreTheme) {
  const { background: _bg, ...rest } = SCORE_COLORS[theme];
  void _bg;
  return rest;
}

export function TabViewer({ tabId }: { tabId: string }) {
  const [tab, setTab] = useState<Tab | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<ScoreTheme>(() => loadScoreTheme());

  useEffect(() => {
    const ctrl = new AbortController();
    getTab(tabId, ctrl.signal)
      .then(setTab)
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Erro ao carregar a tablatura.");
      });
    return () => ctrl.abort();
  }, [tabId]);

  function changeTheme(t: ScoreTheme) {
    setTheme(t);
    saveScoreTheme(t);
  }

  if (error) return <p role="alert" className="error">{error}</p>;
  if (!tab) return <p className="muted" role="status" aria-live="polite">A carregar a tablatura…</p>;

  const info = readScoreInfo(tab.revision.score);
  return (
    <>
      <TabHeader tab={tab} info={info} theme={theme} onTheme={changeTheme} />
      <TabPlayer alphatex={tab.alphatex} theme={theme} />
    </>
  );
}

function TabHeader({
  tab,
  info,
  theme,
  onTheme,
}: {
  tab: Tab;
  info: ScoreInfo;
  theme: ScoreTheme;
  onTheme: (t: ScoreTheme) => void;
}) {
  const tuning = formatTuning(tab.tuning);
  const omitted = info.warnings.length;
  return (
    <header className="tab-header">
      <div className="tab-header-row">
        <div>
          <h1>{tab.title}</h1>
          <div className="chips">
            {tuning && <span className="chip">{tuning}</span>}
            {info.tempo_bpm !== null && (
              <span className="chip mono">
                ♩ {Math.round(info.tempo_bpm)} · {info.time_signature ? info.time_signature.join("/") : "4/4"}
              </span>
            )}
            <span className="chip">{tab.revision.source === "ai" ? "Gerada por IA" : "Editada por si"}</span>
            {tab.revision.source === "ai" && (
              <span className="chip chip-accent">Rascunho IA · verifique ritmo e posições</span>
            )}
          </div>
        </div>
        <div className="tab-actions">
          <div className="segmented-inline" role="group" aria-label="Pauta">
            <span className="seg-label" id="theme-label">Pauta:</span>
            {(["dark", "light"] as const).map((t) => (
              <button
                key={t}
                type="button"
                className="seg-btn"
                aria-pressed={theme === t}
                aria-describedby="theme-label"
                onClick={() => onTheme(t)}
              >
                {t === "dark" ? "Escura" : "Clara"}
              </button>
            ))}
          </div>
          <button type="button" className="btn" disabled title="Em breve">
            Exportar
          </button>
          <Link
            href={`/tabs/${encodeURIComponent(tab.id)}/edit`}
            className="btn btn-primary"
          >
            Editar
          </Link>
        </div>
      </div>
      {omitted > 0 && (
        <p className="muted warn-note">
          {omitted} {omitted === 1 ? "nota não coube" : "notas não couberam"} no braço e{" "}
          {omitted === 1 ? "foi omitida" : "foram omitidas"}.
        </p>
      )}
    </header>
  );
}

function TabPlayer({ alphatex, theme }: { alphatex: string; theme: ScoreTheme }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<AlphaTabApi | null>(null);
  const themeRef = useRef(theme);
  const [rendered, setRendered] = useState(false);
  const [playerReady, setPlayerReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(100);
  const speedRef = useRef(100);
  const [looping, setLooping] = useState(false);
  const [metronome, setMetronome] = useState(false);
  const [pos, setPos] = useState({ cur: 0, end: 0 });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let api: AlphaTabApi | null = null;
    (async () => {
      const at = await import("@coderline/alphatab");
      const host = hostRef.current;
      if (disposed || !host) return;
      api = new at.AlphaTabApi(host, {
        core: {
          fontDirectory: `${ASSET_BASE}/font/`,
          scriptFile: `${ASSET_BASE}/alphaTab.mjs`,
        },
        display: { resources: resourceColors(themeRef.current) },
        player: {
          playerMode: at.PlayerMode.EnabledSynthesizer,
          soundFont: `${ASSET_BASE}/soundfont/sonivox.sf2`,
          // Default (Continuous) scrolls the page to the cursor as soon as the player is
          // ready, hiding the header; only follow the cursor once it leaves the screen.
          scrollMode: at.ScrollMode.OffScreen,
        },
      });
      apiRef.current = api;
      // The page header already shows the title and tuning.
      api.settings.notation.elements.set(at.NotationElement.ScoreTitle, false);
      api.settings.notation.elements.set(at.NotationElement.GuitarTuning, false);
      api.updateSettings();
      api.renderFinished.on(() => setRendered(true));
      api.playerReady.on(() => {
        // Apply a speed chosen while the soundfont was still loading.
        if (api) api.playbackSpeed = speedRef.current / 100;
        setPlayerReady(true);
      });
      api.error.on((e) => {
        console.error("alphaTab error", e);
        setError("Não foi possível apresentar a tablatura.");
      });
      api.playerStateChanged.on((e) => setPlaying(e.state === at.synth.PlayerState.Playing));
      api.playerPositionChanged.on((e) => setPos({ cur: e.currentTime, end: e.endTime }));
      api.tex(alphatex);
    })().catch(() => setError("Não foi possível iniciar o visualizador."));

    return () => {
      disposed = true;
      apiRef.current = null;
      api?.destroy();
    };
  }, [alphatex]);

  // Runtime theme change: update resources in place and re-render.
  useEffect(() => {
    themeRef.current = theme;
    const api = apiRef.current;
    if (!api) return;
    let cancelled = false;
    void import("@coderline/alphatab").then((at) => {
      if (cancelled || apiRef.current !== api) return;
      const res = api.settings.display.resources;
      const c = resourceColors(theme);
      res.mainGlyphColor = at.model.Color.fromJson(c.mainGlyphColor)!;
      res.secondaryGlyphColor = at.model.Color.fromJson(c.secondaryGlyphColor)!;
      res.staffLineColor = at.model.Color.fromJson(c.staffLineColor)!;
      res.barSeparatorColor = at.model.Color.fromJson(c.barSeparatorColor)!;
      res.barNumberColor = at.model.Color.fromJson(c.barNumberColor)!;
      res.scoreInfoColor = at.model.Color.fromJson(c.scoreInfoColor)!;
      api.updateSettings();
      api.render();
    });
    return () => {
      cancelled = true;
    };
  }, [theme]);

  const ready = rendered && playerReady;
  const statusText = error ? "" : !rendered ? "A desenhar a partitura…" : !playerReady ? "A carregar o som…" : "Pronto.";

  return (
    <section aria-label="Leitor de tablatura">
      <p role="status" aria-live="polite" className="muted player-status">
        {statusText}
      </p>
      <p role="alert" className="error">{error}</p>
      <div className="score-card" style={{ background: SCORE_COLORS[theme].background }} data-score-theme={theme}>
        <div ref={hostRef} className="at-host" data-testid="alphatab-host" />
        <div className="player" role="group" aria-label="Controlos de reprodução">
          <button
            type="button"
            className="play-btn"
            disabled={!ready}
            aria-label={playing ? "Pausar" : "Reproduzir"}
            onClick={() => apiRef.current?.playPause()}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
              {playing ? (
                <path d="M4 2h3.5v14H4zM10.5 2H14v14h-3.5z" fill="currentColor" />
              ) : (
                <path d="M5 2l11 7-11 7z" fill="currentColor" />
              )}
            </svg>
          </button>
          <button
            type="button"
            className="icon-btn"
            disabled={!ready}
            aria-label="Parar"
            onClick={() => apiRef.current?.stop()}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <rect x="2" y="2" width="12" height="12" rx="2" fill="currentColor" />
            </svg>
          </button>
          <span className="mono clock" role="timer" aria-label="Posição">
            {formatClock(pos.cur)} / {formatClock(pos.end)}
          </span>
          <label htmlFor="speed" className="speed-label">
            Velocidade <span className="mono">{speed}%</span>
          </label>
          <input
            id="speed"
            type="range"
            min={25}
            max={150}
            step={5}
            value={speed}
            onChange={(e) => {
              const v = Number(e.target.value);
              setSpeed(v);
              speedRef.current = v;
              if (apiRef.current) apiRef.current.playbackSpeed = v / 100;
            }}
          />
          <button
            type="button"
            className="toggle-btn"
            disabled={!ready}
            aria-pressed={looping}
            onClick={() => {
              const v = !looping;
              setLooping(v);
              if (apiRef.current) apiRef.current.isLooping = v;
            }}
          >
            Repetir
          </button>
          <button
            type="button"
            className="toggle-btn"
            disabled={!ready}
            aria-pressed={metronome}
            onClick={() => {
              const v = !metronome;
              setMetronome(v);
              if (apiRef.current) apiRef.current.metronomeVolume = v ? 1 : 0;
            }}
          >
            Metrónomo
          </button>
        </div>
      </div>
    </section>
  );
}
