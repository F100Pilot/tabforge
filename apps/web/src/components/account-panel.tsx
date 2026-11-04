"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { deleteAccount } from "@/lib/api";
import { deleteAccountErrorMessage, emailMatches } from "@/lib/auth-ui";
import { SignInPrompt } from "./sign-in-prompt";
import { useSession } from "./session-provider";

export function AccountPanel() {
  const { status, user, refresh } = useSession();
  const router = useRouter();
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  if (status === "loading") return <p className="muted" role="status">A carregar…</p>;
  if (status === "anonymous" || !user) return <SignInPrompt />;

  const confirmed = emailMatches(typed, user.email);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    try {
      await deleteAccount();
      await refresh();
      router.replace("/?aviso=conta-eliminada");
    } catch (err) {
      setError(deleteAccountErrorMessage(err));
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  return (
    <>
      <section className="card account-card" aria-labelledby="acc-h">
        <h2 id="acc-h">A sua conta</h2>
        <p>
          Email: <strong className="break">{user.email}</strong>
        </p>
      </section>

      <section className="card danger-zone" aria-labelledby="danger-h">
        <h2 id="danger-h">Eliminar conta</h2>
        <p>
          Esta ação elimina de forma permanente a sua conta, o áudio que carregou, todas as suas tabs e os dados
          associados. Não pode ser desfeita.
        </p>
        <form onSubmit={onSubmit} aria-busy={busy}>
          <label className="field field-lg" htmlFor="confirm-email">
            Para confirmar, escreva o seu email ({user.email})
            <input
              ref={inputRef}
              id="confirm-email"
              type="email"
              autoComplete="off"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              disabled={busy}
              aria-describedby="delete-error"
            />
          </label>
          <button type="submit" className="btn btn-danger" disabled={!confirmed || busy}>
            {busy ? "A eliminar…" : "Eliminar conta permanentemente"}
          </button>
          <p role="status" aria-live="polite" className="status">
            {busy ? "A eliminar a conta e os dados…" : ""}
          </p>
          <p id="delete-error" role="alert" className="error">
            {error}
          </p>
        </form>
      </section>
    </>
  );
}
