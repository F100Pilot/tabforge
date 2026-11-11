"use client";

import { useState } from "react";
import { deleteSongMessage } from "@/lib/songs";

/**
 * "Apagar" next to a song card, with a confirmation step (no browser dialog: the desktop
 * window may not show one). `onDelete` removes it on the server; the caller then drops the
 * card from its list.
 */
export function DeleteSong({ title, onDelete }: { title: string; onDelete: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onDelete();
    } catch (err) {
      setError(deleteSongMessage(err));
      setConfirming(false);
      setBusy(false);
    }
  }

  if (!confirming) {
    return (
      <>
        <button
          type="button"
          className="btn btn-small song-delete"
          aria-label={`Apagar ${title}`}
          onClick={() => setConfirming(true)}
        >
          Apagar
        </button>
        {error && (
          <p role="alert" className="error song-error">
            {error}
          </p>
        )}
      </>
    );
  }
  return (
    <div className="song-confirm" role="group" aria-label={`Confirmar apagar ${title}`}>
      <span>Apagar a tab e o áudio desta música?</span>
      <button type="button" className="btn btn-small btn-danger" disabled={busy} onClick={() => void confirm()}>
        {busy ? "A apagar…" : "Apagar"}
      </button>
      <button type="button" className="btn btn-small" disabled={busy} onClick={() => setConfirming(false)}>
        Cancelar
      </button>
    </div>
  );
}
