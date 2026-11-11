"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AlphaTabApi } from "@coderline/alphatab";
import {
  isUnauthenticated,
  ProblemError,
  getTab,
  listRevisions,
  previewScore,
  saveRevision,
  type RevisionSummary,
  type Tab,
} from "@/lib/api";
import {
  MAX_FRET,
  alternatives,
  canRedo,
  canUndo,
  chainOf,
  clampSelection,
  createHistory,
  deleteNote,
  findNote,
  moveToString,
  nextNote,
  noteAbove,
  noteBelow,
  noteName,
  parseScoreDoc,
  pitchOf,
  playableStrings,
  previousNote,
  pushHistory,
  redo,
  setFret,
  typedFret,
  undo,
  type Edit,
  type History,
  type ScoreDoc,
  type TrackBody,
  type Selection,
  type TypeBuffer,
} from "@/lib/editor";
import { scoreTracks, withTrack } from "@/lib/tracks";
import { SignInPrompt } from "./sign-in-prompt";
import { formatDate } from "@/lib/format";
import { loadScoreTheme, SCORE_COLORS, type ScoreTheme } from "@/lib/score-theme";
import { sourceLabel } from "@/lib/refret-view";

const ASSET_BASE = "/alphatab";
const CONFLICT_MESSAGE = "A tab foi alterada noutro lado. Recarregue para ver a versão mais recente.";

export function TabEditor({ tabId }: { tabId: string }) {
  const [tab, setTab] = useState<Tab | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    getTab(tabId, ctrl.signal)
      .then(setTab)
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        if (isUnauthenticated(err)) setNeedsLogin(true);
        else setError(err instanceof Error ? err.message : "Erro ao carregar a tablatura.");
      });
    return () => ctrl.abort();
  }, [tabId]);

  if (needsLogin) return <SignInPrompt />;
  if (error) return <p role="alert" className="error">{error}</p>;
  if (!tab) return <p className="muted" role="status" aria-live="polite">A carregar o editor…</p>;
  let score: ScoreDoc;
  try {
    score = parseScoreDoc(tab.revision.score);
  } catch {
    return <p role="alert" className="error">Esta tablatura não pode ser editada (formato desconhecido).</p>;
  }
  return <EditorBody tab={tab} initialScore={score} />;
}

interface UiState {
  history: History<ScoreDoc>;
  selection: Selection | null;
}

interface Anchor {
  x: number;
  y: number;
  w: number;
  h: number;
  stageW: number;
  stageH: number;
}

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "conflict" }
  | { kind: "error"; message: string };

function resourceColors(theme: ScoreTheme) {
  const { background: _bg, ...rest } = SCORE_COLORS[theme];
  void _bg;
  return rest;
}

function describeError(err: unknown, fallback: string): string {
  if (isUnauthenticated(err)) return "A sessão terminou. Inicie sessão para continuar.";
  return err instanceof Error ? err.message : fallback;
}

/** The editable part ({tuning, bars}) of one track of the score document. */
function trackOf(doc: ScoreDoc, index: number): TrackBody {
  const tracks = scoreTracks(doc);
  return tracks[Math.min(index, tracks.length - 1)];
}

function EditorBody({ tab, initialScore }: { tab: Tab; initialScore: ScoreDoc }) {
  const [ui, setUi] = useState<UiState>({ history: createHistory(initialScore), selection: null });
  const uiRef = useRef(ui);
  const [savedScore, setSavedScore] = useState(initialScore);
  const [revisions, setRevisions] = useState<RevisionSummary[] | null>(null);
  const [revisionsError, setRevisionsError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [renderTick, setRenderTick] = useState(0);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [theme] = useState<ScoreTheme>(() => loadScoreTheme());
  // ADR-0010: the editor edits one track at a time; the others are kept untouched.
  const [trackIndex, setTrackIndex] = useState(0);
  const trackIndexRef = useRef(0);
  const trackNames = useMemo(() => scoreTracks(initialScore).map((t) => t.name), [initialScore]);

  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<AlphaTabApi | null>(null);
  const pendingTexRef = useRef(tab.alphatex);
  const previewInFlightRef = useRef(false);
  const initialScoreRef = useRef(initialScore);
  const typeBufRef = useRef<TypeBuffer | null>(null);
  const typedPushedRef = useRef(false);
  const lastInputEditRef = useRef<{ key: string; at: number } | null>(null);
  const savingRef = useRef(false);

  const { history, selection } = ui;
  const doc = history.present;
  const dirty = doc !== savedScore;
  const score = useMemo(() => trackOf(doc, trackIndex), [doc, trackIndex]);

  const lastSelectionRef = useRef<Selection | null>(null);

  const commit = useCallback((next: UiState) => {
    if (next.selection) lastSelectionRef.current = next.selection;
    uiRef.current = next;
    setUi(next);
  }, []);

  const changeTrack = useCallback(
    (index: number) => {
      if (index === trackIndexRef.current) return;
      trackIndexRef.current = index;
      setTrackIndex(index);
      typeBufRef.current = null;
      lastInputEditRef.current = null;
      commit({ history: uiRef.current.history, selection: null });
      const api = apiRef.current;
      const tracks = api?.score?.tracks;
      if (api && tracks?.[index]) api.renderTracks([tracks[index]]);
    },
    [commit],
  );

  const select = useCallback(
    (sel: Selection | null) => {
      typeBufRef.current = null;
      lastInputEditRef.current = null;
      commit({ history: uiRef.current.history, selection: sel });
    },
    [commit],
  );

  const applyEdit = useCallback(
    (edit: Edit | null, merge = false) => {
      if (!edit) return false;
      const next = withTrack(uiRef.current.history.present, trackIndexRef.current, edit.score);
      commit({ history: pushHistory(uiRef.current.history, next, merge), selection: edit.selection });
      return true;
    },
    [commit],
  );

  const doUndo = useCallback(() => {
    const { history: h, selection: s } = uiRef.current;
    if (!canUndo(h)) return;
    typeBufRef.current = null;
    lastInputEditRef.current = null;
    const nh = undo(h);
    commit({ history: nh, selection: clampSelection(trackOf(nh.present, trackIndexRef.current), s ?? lastSelectionRef.current) });
  }, [commit]);

  const doRedo = useCallback(() => {
    const { history: h, selection: s } = uiRef.current;
    if (!canRedo(h)) return;
    typeBufRef.current = null;
    lastInputEditRef.current = null;
    const nh = redo(h);
    commit({ history: nh, selection: clampSelection(trackOf(nh.present, trackIndexRef.current), s) });
  }, [commit]);

  const refreshRevisions = useCallback(() => {
    listRevisions(tab.id)
      .then((items) => {
        setRevisions(items);
        setRevisionsError(null);
      })
      .catch((err: unknown) => setRevisionsError(describeError(err, "Não foi possível carregar as revisões.")));
  }, [tab.id]);

  useEffect(() => {
    const ctrl = new AbortController();
    listRevisions(tab.id, ctrl.signal)
      .then((items) => setRevisions(items))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setRevisionsError(describeError(err, "Não foi possível carregar as revisões."));
      });
    return () => ctrl.abort();
  }, [tab.id]);

  const save = useCallback(async () => {
    const current = uiRef.current.history.present;
    if (savingRef.current || current === savedScoreRef.current) return;
    savingRef.current = true;
    setSaveState({ kind: "saving" });
    try {
      const saved = await saveRevision(tab.id, baseIdRef.current, current);
      baseIdRef.current = saved.revision.id;
      savedScoreRef.current = current;
      setSavedScore(current);
      setSaveState({ kind: "saved" });
      refreshRevisions();
    } catch (err) {
      if (err instanceof ProblemError && err.status === 409) {
        setSaveState({ kind: "conflict" });
        refreshRevisions();
      }
      else setSaveState({ kind: "error", message: describeError(err, "Não foi possível guardar.") });
    } finally {
      savingRef.current = false;
    }
  }, [tab.id, refreshRevisions]);

  const baseIdRef = useRef(tab.revision.id);
  const savedScoreRef = useRef(savedScore);

  // Warn before leaving with unsaved edits.
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  // alphaTab lifecycle: created once, re-fed with server alphaTex after each edit.
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
          includeNoteBounds: true,
        },
        display: { resources: resourceColors(theme), staveProfile: at.StaveProfile.Tab, scale: 1.3 },
        player: { playerMode: at.PlayerMode.Disabled },
      });
      apiRef.current = api;
      api.settings.notation.elements.set(at.NotationElement.ScoreTitle, false);
      api.settings.notation.elements.set(at.NotationElement.GuitarTuning, false);
      api.updateSettings();
      api.renderFinished.on(() => {
        if (!previewInFlightRef.current) setSyncing(false);
        setRenderTick((n) => n + 1);
      });
      api.error.on((e) => {
        console.error("alphaTab error", e);
        setRenderError("Não foi possível apresentar a tablatura.");
      });
      api.noteMouseDown.on((note) => {
        // Only the track being edited is drawn, but never trust a click on another one.
        if (note.beat.voice.bar.staff.track.index !== trackIndexRef.current) return;
        const current = trackOf(uiRef.current.history.present, trackIndexRef.current);
        const tuningLen = current.tuning.length;
        const sel = clampSelection(current, {
          bar: note.beat.voice.bar.index,
          beat: note.beat.index,
          string: tuningLen + 1 - note.string,
        });
        if (!sel) return;
        // Clamping may relocate to another note; only accept an exact hit.
        if (!findNote(current, sel)) return;
        containerRef.current?.focus({ preventScroll: true });
        select(sel);
      });
      api.beatMouseDown.on((beat) => {
        if (beat && beat.notes.length === 0) select(null);
      });
      api.tex(pendingTexRef.current, [trackIndexRef.current]);
    })().catch(() => setRenderError("Não foi possível iniciar o editor."));
    return () => {
      disposed = true;
      apiRef.current = null;
      api?.destroy();
    };
  }, [theme, select]);

  // Every edit: server-side preview (also validation), then re-render. Last edit wins.
  useEffect(() => {
    if (doc === initialScoreRef.current) return;
    const ctrl = new AbortController();
    previewInFlightRef.current = true;
    const timer = setTimeout(() => {
      setSyncing(true);
      previewScore(tab.id, doc, ctrl.signal)
        .then((tex) => {
          previewInFlightRef.current = false;
          setPreviewError(null);
          pendingTexRef.current = tex;
          if (apiRef.current) apiRef.current.tex(tex, [trackIndexRef.current]);
        })
        .catch((err: unknown) => {
          if (ctrl.signal.aborted) return;
          previewInFlightRef.current = false;
          setSyncing(false);
          setPreviewError(describeError(err, "Não foi possível atualizar a pauta."));
        });
    }, 120);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [doc, tab.id]);

  // Anchor the inspector to the selected note head (also after every render / resize / scroll).
  const computeAnchor = useCallback(() => {
    const api = apiRef.current;
    const stage = stageRef.current;
    const host = hostRef.current;
    const sel = uiRef.current.selection;
    if (!api || !stage || !host || !sel) return setAnchor(null);
    const abScore = api.score;
    const lookup = api.renderer.boundsLookup;
    const abBeat = abScore?.tracks[trackIndexRef.current]?.staves[0]?.bars[sel.bar]?.voices[0]?.beats[sel.beat];
    if (!lookup || !abBeat) return setAnchor(null);
    const tuningLen = trackOf(uiRef.current.history.present, trackIndexRef.current).tuning.length;
    const nb = lookup.findBeat(abBeat)?.notes?.find((n) => n.note.string === tuningLen + 1 - sel.string);
    const surface = host.querySelector<HTMLElement>(".at-surface") ?? host.firstElementChild;
    if (!nb || !surface) return setAnchor(null);
    const s = surface.getBoundingClientRect();
    const st = stage.getBoundingClientRect();
    const b = nb.noteHeadBounds;
    setAnchor({
      x: s.left - st.left + b.x,
      y: s.top - st.top + b.y,
      w: b.w,
      h: b.h,
      stageW: st.width,
      stageH: st.height,
    });
  }, []);

  useEffect(() => {
    computeAnchor();
  }, [selection, renderTick, computeAnchor]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    host.addEventListener("scroll", computeAnchor, { passive: true });
    return () => host.removeEventListener("scroll", computeAnchor);
  }, [computeAnchor]);

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const target = e.target as HTMLElement;
    const typing = target.closest("input, select, textarea, [contenteditable='true']") !== null;
    const mod = e.ctrlKey || e.metaKey;
    const key = e.key;
    if (mod && !e.altKey && key.toLowerCase() === "s") {
      e.preventDefault();
      void save();
      return;
    }
    if (typing || e.altKey) return;
    if (mod) {
      const k = key.toLowerCase();
      if (k === "z") {
        e.preventDefault();
        if (e.shiftKey) doRedo();
        else doUndo();
      } else if (k === "y") {
        e.preventDefault();
        doRedo();
      }
      return;
    }
    const { history: h, selection: sel } = uiRef.current;
    const sc = trackOf(h.present, trackIndexRef.current);
    const move = (to: Selection | null) => {
      e.preventDefault();
      if (to) select(to);
    };
    if (key === "Escape") {
      if (sel) select(null);
      return;
    }
    if (key === "ArrowLeft" || key === "ArrowRight" || key === "ArrowUp" || key === "ArrowDown") {
      if (!sel) return;
      if (key === "ArrowLeft") move(previousNote(sc, sel));
      else if (key === "ArrowRight") move(nextNote(sc, sel));
      else if (key === "ArrowUp") move(noteAbove(sc, sel));
      else move(noteBelow(sc, sel));
      return;
    }
    if (!sel) return;
    if (key === "Delete" || key === "Backspace") {
      e.preventDefault();
      typeBufRef.current = null;
      lastInputEditRef.current = null;
      applyEdit(deleteNote(sc, sel));
      return;
    }
    if (/^[0-9]$/.test(key) && !e.shiftKey) {
      e.preventDefault();
      lastInputEditRef.current = null;
      const r = typedFret(typeBufRef.current, Number(key), Date.now());
      typeBufRef.current = r.buffer;
      if (r.fret === null) return;
      const merge = r.merge && typedPushedRef.current;
      const ok = applyEdit(setFret(sc, sel, r.fret), merge);
      if (!r.merge) typedPushedRef.current = ok;
    }
  }

  const info = useMemo(() => {
    if (!selection) return null;
    const note = findNote(score, selection);
    if (!note) return null;
    const pitch = pitchOf(score, selection.string, note.fret);
    return {
      note,
      pitch,
      strings: playableStrings(score, selection),
      alts: alternatives(score, selection),
      tied: (chainOf(score, selection)?.length ?? 1) > 1,
      duration: score.bars[selection.bar].beats[selection.beat].duration,
    };
  }, [score, selection]);

  const statusText =
    saveState.kind === "saving"
      ? "A guardar…"
      : saveState.kind === "saved" && !dirty
        ? "Revisão guardada."
        : syncing
          ? "A atualizar a pauta…"
          : "";

  return (
    <div
      ref={containerRef}
      className="editor"
      tabIndex={0}
      role="group"
      aria-label="Editor de tablatura"
      onKeyDown={onKeyDown}
    >
      <header className="editor-header">
        <Link href={`/tabs/${encodeURIComponent(tab.id)}`} className="btn back-link">
          <span aria-hidden="true">←</span> Voltar à tab
        </Link>
        <h1 className="editor-title">{tab.title}</h1>
        <span className={dirty ? "pill pill-dirty" : "pill pill-hidden"} aria-hidden={!dirty}>
          Por guardar
        </span>
        <div className="editor-actions">
          <button type="button" className="btn" disabled={!canUndo(history)} onClick={doUndo}>
            <span aria-hidden="true">↶ </span>Anular
          </button>
          <button type="button" className="btn" disabled={!canRedo(history)} onClick={doRedo}>
            <span aria-hidden="true">↷ </span>Refazer
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!dirty || saveState.kind === "saving" || saveState.kind === "conflict"}
            onClick={() => void save()}
          >
            Guardar revisão
          </button>
        </div>
      </header>

      {trackNames.length > 1 && (
        <div className="segmented-inline track-picker" role="group" aria-label="Pista a editar">
          <span className="seg-label" id="edit-track-label">Pista a editar:</span>
          {trackNames.map((name, i) => (
            <button
              key={`${i}-${name}`}
              type="button"
              className="seg-btn"
              aria-pressed={trackIndex === i}
              aria-describedby="edit-track-label"
              onClick={() => changeTrack(i)}
            >
              {name}
            </button>
          ))}
        </div>
      )}

      <div className="duration-bar" role="toolbar" aria-label="Durações (em breve)">
        <span className="seg-label">Duração</span>
        {[
          ["1", 1, "Semibreve"],
          ["1/2", 2, "Mínima"],
          ["1/4", 4, "Semínima"],
          ["1/8", 8, "Colcheia"],
          ["1/16", 16, "Semicolcheia"],
          ["1/32", 32, "Fusa"],
        ].map(([label, value, name]) => (
          <button
            key={label as string}
            type="button"
            className="dur-btn mono"
            disabled
            title="Em breve"
            aria-label={`${name as string} (em breve)`}
            aria-pressed={info?.duration === value}
          >
            {label}
          </button>
        ))}
        <button type="button" className="dur-btn mono" disabled title="Em breve" aria-label="Ponto (em breve)">
          •
        </button>
      </div>

      <div className="editor-status" aria-live="polite">
        {statusText}
      </div>
      {previewError && (
        <p role="alert" className="error">
          {previewError}
        </p>
      )}
      {renderError && (
        <p role="alert" className="error">
          {renderError}
        </p>
      )}
      {saveState.kind === "error" && (
        <p role="alert" className="error">
          {saveState.message}
        </p>
      )}
      {saveState.kind === "conflict" && (
        <div role="alert" className="conflict">
          <span>{CONFLICT_MESSAGE}</span>
          <button type="button" className="btn" onClick={() => window.location.reload()}>
            Recarregar
          </button>
        </div>
      )}

      <div className="editor-grid">
        <div className="editor-main">
          <div
            ref={stageRef}
            className="score-card editor-stage"
            style={{ background: SCORE_COLORS[theme].background }}
            data-score-theme={theme}
          >
            <div ref={hostRef} className="at-host at-host-edit" data-testid="alphatab-host" />
            {anchor && info && selection && (
              <>
                <div
                  className="note-marker"
                  aria-hidden="true"
                  style={{ left: anchor.x - 4, top: anchor.y - 3, width: anchor.w + 8, height: anchor.h + 6 }}
                />
                <Inspector
                  key={`${selection.bar}.${selection.beat}.${selection.string}`}
                  score={score}
                  selection={selection}
                  info={info}
                  anchor={anchor}
                  onFret={(fret) => {
                    const key = `${selection.bar}.${selection.beat}.${selection.string}`;
                    const now = Date.now();
                    const last = lastInputEditRef.current;
                    const merge = !!last && last.key === key && now - last.at < 1000;
                    if (applyEdit(setFret(score, selection, fret), merge)) {
                      lastInputEditRef.current = { key, at: now };
                    }
                  }}
                  onString={(str) => {
                    lastInputEditRef.current = null;
                    applyEdit(moveToString(score, selection, str));
                  }}
                  onDelete={() => {
                    lastInputEditRef.current = null;
                    applyEdit(deleteNote(score, selection));
                    containerRef.current?.focus({ preventScroll: true });
                  }}
                />
              </>
            )}
          </div>
          {!selection && <p className="muted editor-hint">Clique numa nota da pauta para a editar.</p>}
          <KeyHints />
        </div>

        <aside className="editor-rail card" aria-label="Revisões">
          <h2>Revisões</h2>
          {revisionsError && <p className="error" role="alert">{revisionsError}</p>}
          {!revisions && !revisionsError && <p className="muted">A carregar…</p>}
          {revisions && (
            <ol className="timeline">
              {revisions.map((r, i) => (
                <li key={r.id} className={i === 0 ? "tl-item tl-current" : "tl-item"}>
                  <span className="tl-dot" aria-hidden="true" />
                  <div>
                    <div className="tl-title">
                      {sourceLabel(r.source)}
                      {i === 0 && <span className="chip chip-accent tl-badge">atual</span>}
                    </div>
                    <div className="muted tl-date">{formatDate(r.created_at)}</div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </aside>
      </div>
    </div>
  );
}

function Inspector({
  score,
  selection,
  info,
  anchor,
  onFret,
  onString,
  onDelete,
}: {
  score: TrackBody;
  selection: Selection;
  info: { note: { fret: number }; pitch: number; strings: number[]; alts: Array<{ string: number; fret: number }>; tied: boolean };
  anchor: Anchor;
  onFret: (fret: number) => void;
  onString: (str: number) => void;
  onDelete: () => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const width = 288;
  const left = Math.max(8, Math.min(anchor.x + anchor.w / 2 - width / 2, anchor.stageW - width - 8));
  const below = anchor.y + anchor.h + 12;
  const flip = below + 270 > anchor.stageH && anchor.y > 280;
  const style: React.CSSProperties = flip
    ? { left, width, top: anchor.y - 12, transform: "translateY(-100%)" }
    : { left, width, top: below };
  const value = draft ?? String(info.note.fret);
  const parsed = value.trim() === "" ? NaN : Number(value);
  const invalid = draft !== null && !(Number.isInteger(parsed) && parsed >= 0 && parsed <= MAX_FRET);
  const name = noteName(info.pitch);
  return (
    <div className="inspector" role="dialog" aria-modal="false" aria-labelledby="insp-title" style={style}>
      <div className="insp-head">
        <h2 id="insp-title" className="insp-name">
          {name}
        </h2>
        <span className="muted insp-pos">
          Compasso {selection.bar + 1} · tempo {selection.beat + 1}
        </span>
      </div>
      <div className="insp-fields">
        <label className="field">
          <span>Corda</span>
          <select
            value={selection.string}
            onChange={(e) => onString(Number(e.target.value))}
            aria-label="Corda"
          >
            {info.strings.map((s) => (
              <option key={s} value={s}>
                {s} ({noteName(score.tuning[s - 1])})
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Traste</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_FRET}
            step={1}
            value={value}
            aria-invalid={invalid}
            onChange={(e) => {
              setDraft(e.target.value);
              const n = Number(e.target.value);
              if (e.target.value.trim() !== "" && Number.isInteger(n) && n >= 0 && n <= MAX_FRET) onFret(n);
            }}
            onBlur={() => setDraft(null)}
          />
        </label>
      </div>
      {invalid && <p className="error insp-note">O traste deve estar entre 0 e {MAX_FRET}.</p>}
      {info.tied && <p className="muted insp-note">Nota ligada: a edição aplica-se a toda a ligadura.</p>}
      {info.alts.length > 0 && (
        <div className="insp-alts" role="group" aria-label="Mesma nota noutra posição">
          <span className="seg-label">Mesma nota noutra posição</span>
          <div className="alt-chips">
            {info.alts.map((a) => (
              <button
                key={a.string}
                type="button"
                className="alt-chip"
                aria-label={`Mover para a corda ${a.string}, traste ${a.fret}`}
                onClick={() => onString(a.string)}
              >
                <span className="mono">
                  {a.string} · {a.fret}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      <button type="button" className="btn btn-danger insp-delete" onClick={onDelete}>
        Apagar nota
      </button>
    </div>
  );
}

function KeyHints() {
  const items: Array<[string[], string]> = [
    [["←", "→"], "nota anterior / seguinte"],
    [["↑", "↓"], "nota do acorde"],
    [["0–9"], "escrever traste"],
    [["Del"], "apagar nota"],
    [["Ctrl", "Z"], "anular"],
    [["Ctrl", "⇧", "Z"], "refazer"],
    [["Ctrl", "S"], "guardar"],
  ];
  return (
    <ul className="keyhints" aria-label="Atalhos de teclado">
      {items.map(([keys, label]) => (
        <li key={label}>
          <span className="keys">
            {keys.map((k) => (
              <kbd key={k}>{k}</kbd>
            ))}
          </span>{" "}
          <span className="muted">{label}</span>
        </li>
      ))}
    </ul>
  );
}
