"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { requestMagicLink } from "@/lib/api";
import { magicLinkErrorMessage } from "@/lib/auth-ui";

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sentRef = useRef<HTMLParagraphElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (sentTo) sentRef.current?.focus();
  }, [sentTo]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = email.trim();
    if (!value) {
      setError("Introduza o seu email.");
      inputRef.current?.focus();
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await requestMagicLink(value);
      setSentTo(value);
    } catch (err) {
      setError(magicLinkErrorMessage(err));
      inputRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  if (sentTo) {
    return (
      <div className="card auth-card">
        <p ref={sentRef} tabIndex={-1} role="status" className="auth-sent">
          Enviámos um link para <strong className="break">{sentTo}</strong>. Abra-o neste dispositivo para entrar.
        </p>
        <p className="note">Não chegou? Verifique o spam ou peça um novo link.</p>
        <button type="button" className="btn" onClick={() => setSentTo(null)}>
          Usar outro email
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} aria-busy={busy} className="card auth-card" noValidate>
      <label className="field field-lg" htmlFor="login-email">
        Email
        <input
          ref={inputRef}
          id="login-email"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy}
          aria-invalid={error ? true : undefined}
          aria-describedby="login-error"
        />
      </label>
      <p className="note">Sem palavra-passe: enviamos-lhe um link de acesso por email.</p>
      <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
        {busy ? "A enviar…" : "Enviar link de acesso"}
      </button>
      <p id="login-error" role="alert" className="error">
        {error}
      </p>
    </form>
  );
}
