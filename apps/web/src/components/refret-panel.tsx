"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getTuning, refretTab, type Tab } from "@/lib/api";
import { refretMessage, refretProblemMessage } from "@/lib/refret-view";

/**
 * ADR-0016: "Refazer as posições com o que aprendi". Shown only while learned weights are in
 * use; the new revision replaces the tab in the viewer (and the comparison reloads with it).
 */
export function RefretPanel({ tab, onTabChanged }: { tab: Tab; onTabChanged: (tab: Tab) => void }) {
  const [inUse, setInUse] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getTuning(ctrl.signal)
      .then((t) => setInUse(t.in_use))
      .catch(() => setInUse(false)); // no card if the profile cannot be read
    return () => ctrl.abort();
  }, []);

  if (!inUse) return null;

  async function refret() {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const r = await refretTab(tab.id, tab.revision.id);
      setMessage(refretMessage(r.changed));
      if (r.changed > 0) onTabChanged(r.tab);
    } catch (err) {
      setError(refretProblemMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card refret" aria-labelledby="refret-h">
      <h2 id="refret-h">Aprendizagem</h2>
      <p className="muted">
        O TabForge aprendeu com as suas tabs certas a escolher cordas e trastes (
        <Link href="/aprendizagem">ver</Link>). Pode aplicar isso a esta tab: as notas e o ritmo ficam
        iguais.
      </p>
      <button type="button" className="btn" disabled={busy} onClick={() => void refret()}>
        {busy ? "A refazer…" : "Refazer as posições com o que aprendi"}
      </button>
      <p role="status" aria-live="polite" className="status">
        {message}
      </p>
      <p role="alert" className="error">
        {error}
      </p>
    </section>
  );
}
