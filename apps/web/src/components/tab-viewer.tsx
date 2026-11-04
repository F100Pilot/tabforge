"use client";

import { useEffect, useRef, useState } from "react";
import type { AlphaTabApi } from "@coderline/alphatab";
import { getTab, type Tab } from "@/lib/api";

const ASSET_BASE = "/alphatab";

export function TabViewer({ tabId }: { tabId: string }) {
  const [tab, setTab] = useState<Tab | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  if (error) return <p role="alert" className="error">{error}</p>;
  if (!tab) return <p role="status" aria-live="polite">A carregar a tablatura…</p>;
  return (
    <>
      <h1>{tab.title}</h1>
      <TabPlayer alphatex={tab.alphatex} />
    </>
  );
}

function TabPlayer({ alphatex }: { alphatex: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<AlphaTabApi | null>(null);
  const [rendered, setRendered] = useState(false);
  const [playerReady, setPlayerReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(100);
  const speedRef = useRef(100);
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
        player: {
          playerMode: at.PlayerMode.EnabledSynthesizer,
          soundFont: `${ASSET_BASE}/soundfont/sonivox.sf2`,
        },
      });
      apiRef.current = api;
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
      api.tex(alphatex);
    })().catch(() => setError("Não foi possível iniciar o visualizador."));

    return () => {
      disposed = true;
      apiRef.current = null;
      api?.destroy();
    };
  }, [alphatex]);

  const ready = rendered && playerReady;

  return (
    <section aria-label="Leitor de tablatura">
      <div className="controls">
        <button type="button" disabled={!ready} onClick={() => apiRef.current?.playPause()}>
          {playing ? "Pausar" : "Reproduzir"}
        </button>
        <button type="button" disabled={!ready} onClick={() => apiRef.current?.stop()}>
          Parar
        </button>
        <label htmlFor="speed">Velocidade: {speed}%</label>
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
      </div>
      <p role="status" aria-live="polite" className="status">
        {error ? "" : !rendered ? "A desenhar a partitura…" : !playerReady ? "A carregar o som…" : "Pronto."}
      </p>
      <p role="alert" className="error">{error}</p>
      <div ref={hostRef} className="at-host" data-testid="alphatab-host" />
    </section>
  );
}
