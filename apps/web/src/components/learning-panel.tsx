"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getTuning, isUnauthenticated, requestTuning, type Tuning } from "@/lib/api";
import {
  POLL_INTERVAL_MS,
  accuracyLine,
  shouldPoll,
  statusLine,
  tuningProblemMessage,
  inUseLine,
  weightRows,
} from "@/lib/tuning-view";
import { SignInPrompt } from "./sign-in-prompt";

/** ADR-0011: what the TabForge learned from the user's right tabs and corrections. */
export function LearningPanel() {
  const [tuning, setTuning] = useState<Tuning | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [anonymous, setAnonymous] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Start of the current "stale" wait; polling gives up POLL_MAX_MS after it.
  const staleSince = useRef<number | null>(null);
  const [gaveUp, setGaveUp] = useState(false);

  const apply = useCallback((t: Tuning) => {
    if (t.status === "stale") {
      if (staleSince.current === null) staleSince.current = Date.now();
    } else {
      staleSince.current = null;
      setGaveUp(false);
    }
    setTuning(t);
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    getTuning(ctrl.signal)
      .then(apply)
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        if (isUnauthenticated(err)) setAnonymous(true);
        else setError(tuningProblemMessage(err));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoaded(true);
      });
    return () => ctrl.abort();
  }, [apply]);

  const status = tuning?.status;
  useEffect(() => {
    if (status !== "stale") return;
    const ctrl = new AbortController();
    const id = window.setInterval(() => {
      const since = staleSince.current ?? Date.now();
      if (!shouldPoll("stale", Date.now() - since)) {
        window.clearInterval(id);
        setGaveUp(true);
        return;
      }
      getTuning(ctrl.signal)
        .then((t) => {
          if (!ctrl.signal.aborted) apply(t);
        })
        .catch(() => {
          /* transient: try again at the next tick */
        });
    }, POLL_INTERVAL_MS);
    return () => {
      ctrl.abort();
      window.clearInterval(id);
    };
  }, [status, apply]);

  async function refresh() {
    setBusy(true);
    setError(null);
    setGaveUp(false);
    staleSince.current = null;
    try {
      apply(await requestTuning());
    } catch (err) {
      if (isUnauthenticated(err)) setAnonymous(true);
      else setError(tuningProblemMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (anonymous) return <SignInPrompt />;
  if (!loaded) return <p className="muted" role="status">A carregar…</p>;
  if (!tuning) {
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  }

  const accuracy = accuracyLine(tuning);
  const use = inUseLine(tuning);
  const rows = weightRows(tuning);
  const stale = tuning.status === "stale" && !gaveUp;
  return (
    <section className="card learning-card" aria-labelledby="learn-h" aria-busy={stale || busy}>
      <h2 id="learn-h">Aprendizagem</h2>
      <p className="learning-status" role="status" aria-live="polite">
        {gaveUp ? "A aprendizagem está a demorar; volte a abrir esta página mais tarde." : statusLine(tuning)}
      </p>
      {accuracy && <p className="mono learning-accuracy">{accuracy}</p>}
      {use && <p>{use}</p>}
      <p className="muted learning-hint">
        O TabForge ajusta a escolha de corda e traste com as tabs certas que importa e com as correções que faz. As
        tabs já geradas não mudam sozinhas.
      </p>
      {rows.length > 0 && (
        <details className="learning-details">
          <summary>Detalhes técnicos</summary>
          <dl className="learning-weights">
            {rows.map((r) => (
              <div key={r.key}>
                <dt>{r.label}</dt>
                <dd className="mono">{r.value}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
      <div>
        <button type="button" className="btn btn-primary" disabled={busy || stale} onClick={() => void refresh()}>
          {busy ? "A pedir…" : "Atualizar agora"}
        </button>
      </div>
      <p role="alert" className="error">
        {error}
      </p>
    </section>
  );
}
