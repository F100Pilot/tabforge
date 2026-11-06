"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type * as AlphaTab from "@coderline/alphatab";
import {
  applyCorrections,
  deleteReference,
  getComparison,
  getReference,
  isUnauthenticated,
  putReference,
  type Comparison,
  type Tab,
  type ReferenceSummary,
} from "@/lib/api";
import {
  alignmentNotes,
  applyResultMessage,
  conflictMessage,
  correctionsSummary,
  describeDifference,
  barDescription,
  barRatio,
  formatDecimal,
  formatPercent,
  referenceProblemMessage,
} from "@/lib/comparison-view";
import { matchingTrackIndex } from "@/lib/tracks";
import {
  hasReferenceExtension,
  MAX_REFERENCE_FILE_BYTES,
  MAX_REFERENCE_NOTES,
  readReferenceTracks,
  referenceNotes,
  REFERENCE_EXTENSIONS,
  type ReferenceTrack,
} from "@/lib/reference";

interface Pending {
  filename: string;
  score: AlphaTab.model.Score;
  tracks: ReferenceTrack[];
}

type Busy = "loading" | "reading" | "sending" | "removing" | "applying" | null;

const LIST_LIMIT = 50;

/** ADR-0009: compare the generated tab with the right one (a Guitar Pro file read in the browser). */
export function TabCompare({
  tabId,
  revisionKey,
  trackNames,
  onTabChanged,
}: {
  tabId: string;
  revisionKey: string;
  /** Names of the tab's own tracks (ADR-0010); each one keeps its own reference. */
  trackNames: string[];
  /** Called with the new tab when applying corrections created a revision, so the viewer reloads it. */
  onTabChanged?: (tab: Tab) => void;
}) {
  const [tabTrack, setTabTrack] = useState(0);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [reference, setReference] = useState<ReferenceSummary | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [trackIndex, setTrackIndex] = useState(0);
  const [busy, setBusy] = useState<Busy>("loading");
  const [error, setError] = useState<string | null>(null);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [learns, setLearns] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    Promise.all([getReference(tabId, tabTrack, ctrl.signal), getComparison(tabId, tabTrack, ctrl.signal)])
      .then(([ref, cmp]) => {
        setReference(ref);
        setComparison(cmp);
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted || isUnauthenticated(err)) return;
        setError(referenceProblemMessage(err));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setBusy(null);
      });
    return () => ctrl.abort();
  }, [tabId, revisionKey, tabTrack]);

  function chooseTabTrack(index: number) {
    if (index === tabTrack) return;
    setReference(null);
    setComparison(null);
    setPending(null);
    setError(null);
    setApplyMessage(null);
    setApplyError(null);
    setLearns(false);
    setBusy("loading");
    setTabTrack(index);
  }

  async function onFile(file: File | undefined) {
    if (inputRef.current) inputRef.current.value = "";
    if (!file) return;
    setError(null);
    setPending(null);
    if (!hasReferenceExtension(file.name) || file.size > MAX_REFERENCE_FILE_BYTES) {
      setError(
        file.size > MAX_REFERENCE_FILE_BYTES
          ? "O ficheiro é demasiado grande."
          : `Escolha um ficheiro Guitar Pro (${REFERENCE_EXTENSIONS.join(", ")}).`,
      );
      return;
    }
    setBusy("reading");
    try {
      const at = await import("@coderline/alphatab");
      const bytes = new Uint8Array(await file.arrayBuffer());
      let read;
      try {
        read = readReferenceTracks(at, bytes);
      } catch (err) {
        console.error("reference read failed", err);
        setError("Não foi possível ler o ficheiro Guitar Pro.");
        setBusy(null);
        return;
      }
      if (read.tracks.length === 0) {
        setError("Este ficheiro não tem nenhuma pista de guitarra com 6 cordas.");
        setBusy(null);
        return;
      }
      const next = { filename: file.name, score: read.score, tracks: read.tracks };
      if (read.tracks.length === 1) {
        await send(next, read.tracks[0]);
      } else {
        // Lead compares with a reference track called Lead, Rhythm with Rhythm, when there is one.
        setTrackIndex(matchingTrackIndex(trackNames[tabTrack] ?? "", read.tracks) ?? read.tracks[0].index);
        setPending(next);
        setBusy(null);
      }
    } catch (err) {
      console.error("reference failed", err);
      setError("Não foi possível ler o ficheiro Guitar Pro.");
      setBusy(null);
    }
  }

  async function send(p: Pending, track: ReferenceTrack) {
    setError(null);
    setBusy("sending");
    try {
      const notes = referenceNotes(p.score, track.index);
      if (notes.length === 0) {
        setError("A pista escolhida não tem notas.");
        return;
      }
      if (notes.length > MAX_REFERENCE_NOTES) {
        setError(`A pista tem notas a mais (máximo ${MAX_REFERENCE_NOTES}).`);
        return;
      }
      const summary = await putReference(tabId, { filename: p.filename, track: track.name, notes }, tabTrack);
      const cmp = await getComparison(tabId, tabTrack);
      setReference(summary);
      setComparison(cmp);
      setPending(null);
      setLearns(true);
    } catch (err) {
      setError(referenceProblemMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    setError(null);
    setBusy("removing");
    try {
      await deleteReference(tabId, tabTrack);
      setReference(null);
      setComparison(null);
      setPending(null);
    } catch (err) {
      setError(referenceProblemMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function applyPositions() {
    setApplyMessage(null);
    setApplyError(null);
    setBusy("applying");
    try {
      const r = await applyCorrections(tabId, tabTrack, revisionKey, ["position"]);
      setApplyMessage(applyResultMessage(r.applied, r.skipped, r.retuned_to));
      if (r.applied > 0 || r.retuned_to) {
        onTabChanged?.(r.tab);
        setLearns(true);
      }
      setComparison(await getComparison(tabId, tabTrack));
    } catch (err) {
      if (isUnauthenticated(err)) setApplyError("A sessão expirou. Entre outra vez.");
      else setApplyError(conflictMessage(err) ?? referenceProblemMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const working = busy !== null;
  const status =
    busy === "loading"
      ? "A verificar a comparação…"
      : busy === "reading"
        ? "A ler o ficheiro…"
        : busy === "sending"
          ? "A comparar…"
          : busy === "removing"
            ? "A remover…"
            : busy === "applying"
              ? "A aplicar correções…"
              : "";

  const hasResult = comparison !== null;
  return (
    <section className="card compare" aria-labelledby="compare-title">
      <div className="compare-head">
        <h2 id="compare-title">Comparar com a tab certa</h2>
        <div className="compare-actions">
          <button type="button" className="btn" disabled={working} onClick={() => inputRef.current?.click()}>
            {hasResult || reference ? "Trocar ficheiro" : "Escolher ficheiro Guitar Pro"}
          </button>
          {(hasResult || reference) && (
            <button type="button" className="btn" disabled={working} onClick={() => void remove()}>
              Remover comparação
            </button>
          )}
        </div>
        <input
          ref={inputRef}
          type="file"
          className="sr-only"
          tabIndex={-1}
          aria-label="Ficheiro Guitar Pro da tab certa"
          accept={REFERENCE_EXTENSIONS.join(",")}
          onChange={(e) => void onFile(e.target.files?.[0])}
        />
      </div>

      {trackNames.length > 1 && (
        <div className="compare-track">
          <label htmlFor="compare-tab-track">Comparar a pista:</label>
          <select
            id="compare-tab-track"
            value={tabTrack}
            disabled={working}
            onChange={(e) => chooseTabTrack(Number(e.target.value))}
          >
            {trackNames.map((name, i) => (
              <option key={`${i}-${name}`} value={i}>
                {name}
              </option>
            ))}
          </select>
        </div>
      )}

      <p role="status" aria-live="polite" className="muted compare-status">
        {status}
      </p>
      <p role="alert" className="error">{error}</p>

      {pending && (
        <form
          className="compare-pick"
          onSubmit={(e) => {
            e.preventDefault();
            const track = pending.tracks.find((t) => t.index === trackIndex) ?? pending.tracks[0];
            void send(pending, track);
          }}
        >
          <label htmlFor="compare-track">Pista de guitarra em {pending.filename}</label>
          <select
            id="compare-track"
            value={trackIndex}
            disabled={working}
            onChange={(e) => setTrackIndex(Number(e.target.value))}
          >
            {pending.tracks.map((t) => (
              <option key={t.index} value={t.index}>
                {t.name}
              </option>
            ))}
          </select>
          <button type="submit" className="btn btn-primary" disabled={working}>
            Comparar
          </button>
        </form>
      )}

      {!hasResult && !reference && busy === null && !pending && (
        <p className="muted">
          Escolha o ficheiro Guitar Pro (.gp, .gp3, .gp4, .gp5, .gpx) com a tab certa desta música. O ficheiro é lido
          no seu browser; só as notas são guardadas.
        </p>
      )}

      {hasResult && (
        <ComparisonResult
          cmp={comparison}
          reference={reference}
          working={working}
          onApply={() => void applyPositions()}
          applyMessage={applyMessage}
          applyError={applyError}
        />
      )}
      {learns && (
        <p className="muted compare-learn">
          O TabForge vai aprender com esta comparação. <Link href="/aprendizagem">Ver a aprendizagem</Link>
        </p>
      )}
      <p className="muted compare-limit">Repetições da tab certa não são expandidas.</p>
    </section>
  );
}

function ComparisonResult({
  cmp,
  reference,
  working,
  onApply,
  applyMessage,
  applyError,
}: {
  cmp: Comparison;
  reference: ReferenceSummary | null;
  working: boolean;
  onApply: () => void;
  applyMessage: string | null;
  applyError: string | null;
}) {
  const align = alignmentNotes(cmp);
  return (
    <div className="compare-result">
      {reference && (
        <p className="muted">
          <span className="mono">{reference.filename}</span> · {reference.track} · {reference.notes} notas
        </p>
      )}
      <dl className="compare-metrics">
        <Metric label="Notas encontradas" value={formatPercent(cmp.recall)} hint={`${cmp.matched} de ${cmp.reference_notes}`} />
        <Metric label="Notas a mais" value={formatPercent(1 - cmp.precision)} hint={`${cmp.ai_notes - cmp.matched} de ${cmp.ai_notes}`} />
        <Metric label="Posição correta" value={formatPercent(cmp.position_accuracy)} hint="corda e traste" />
        <Metric
          label="Desvio médio de ataque"
          value={cmp.onset_error === null ? "—" : `≈ ${formatDecimal(cmp.onset_error)} tempo`}
          hint="nas notas encontradas"
        />
      </dl>
      {align.length > 0 && (
        <ul className="compare-align">
          {align.map((a) => (
            <li key={a} className="chip chip-accent">{a}</li>
          ))}
        </ul>
      )}
      <Corrections
        d={cmp.differences}
        working={working}
        onApply={onApply}
        message={applyMessage}
        error={applyError}
      />
      {cmp.bars.length > 0 && <BarStrip bars={cmp.bars} />}
    </div>
  );
}

function Corrections({
  d,
  working,
  onApply,
  message,
  error,
}: {
  d: Comparison["differences"];
  working: boolean;
  onApply: () => void;
  message: string | null;
  error: string | null;
}) {
  const shown = d.items.slice(0, LIST_LIMIT);
  const hidden = d.counts.position + d.counts.missing + d.counts.extra + d.counts.timing - shown.length;
  return (
    <div className="corrections">
      <h3 className="compare-sub" id="corrections-title">Correções detetadas</h3>
      <p className="corrections-summary">{correctionsSummary(d.counts)}</p>
      {shown.length > 0 && (
        <details className="corrections-list">
          <summary>Ver diferenças ({d.items.length}{d.truncated ? "+" : ""})</summary>
          <ul aria-labelledby="corrections-title">
            {shown.map((it, i) => (
              <li key={`${it.kind}-${it.bar}-${it.onset}-${it.pitch}-${i}`} className={`diff diff-${it.kind}`}>
                {describeDifference(it)}
              </li>
            ))}
          </ul>
          {hidden > 0 && (
            <p className="muted compare-legend">
              … e mais {hidden}
              {d.truncated ? " (lista truncada pelo servidor)" : ""}
            </p>
          )}
        </details>
      )}
      <div className="corrections-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={working || d.counts.position === 0}
          onClick={onApply}
        >
          Aplicar correções de posição ({d.counts.position})
        </button>
      </div>
      <p role="status" aria-live="polite" className="corrections-result">{message}</p>
      <p role="alert" className="error">{error}</p>
      <p className="muted compare-limit">Notas em falta ou a mais ficam só detetadas: corrigi-las muda os compassos.</p>
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="metric">
      <dt>{label}</dt>
      <dd>
        <span className="metric-value mono">{value}</span>
        <span className="muted metric-hint">{hint}</span>
      </dd>
    </div>
  );
}

function BarStrip({ bars }: { bars: Comparison["bars"] }) {
  return (
    <div>
      <h3 className="compare-sub" id="compare-bars">Compassos da tab certa</h3>
      <p className="muted compare-legend">
        Verde: notas encontradas. Vermelho: notas em falta. Cinzento: compasso sem notas.
      </p>
      <ol className="bar-strip" aria-labelledby="compare-bars">
        {bars.map((b) => {
          const ratio = barRatio(b);
          const text = barDescription(b);
          return (
            <li
              key={b.bar}
              className={ratio === null ? "bar-cell bar-empty" : "bar-cell"}
              tabIndex={0}
              title={text}
              aria-label={text}
              style={
                ratio === null
                  ? undefined
                  : { background: `color-mix(in srgb, var(--ok) ${Math.round(ratio * 100)}%, var(--error))` }
              }
            >
              <span aria-hidden="true">{b.bar}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
