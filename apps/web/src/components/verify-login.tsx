"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { verifyLogin } from "@/lib/api";
import { tokenFromHash, verifyErrorKind } from "@/lib/auth-ui";
import { useSession } from "./session-provider";

type Phase = "reading" | "ready" | "missing" | "busy" | "invalid" | "failed";

export function VerifyLogin() {
  const router = useRouter();
  const { refresh } = useSession();
  const [token, setToken] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("reading");

  // The token lives in the URL fragment (never sent to a server); read it once, then strip it from the address bar.
  useEffect(() => {
    const t = tokenFromHash(window.location.hash);
    if (t) window.history.replaceState(null, "", window.location.pathname + window.location.search);
    queueMicrotask(() => {
      setToken(t);
      setPhase(t ? "ready" : "missing");
    });
  }, []);

  async function onEnter() {
    if (!token) return;
    setPhase("busy");
    try {
      await verifyLogin(token);
      await refresh();
      router.replace("/");
    } catch (err) {
      setPhase(verifyErrorKind(err));
    }
  }

  if (phase === "reading") return <p className="muted" role="status">A carregar…</p>;

  if (phase === "missing" || phase === "invalid") {
    return (
      <div className="card auth-card" role="alert">
        <p className="error-text">
          {phase === "invalid" ? "O link expirou ou já foi usado." : "Este link não é válido."}
        </p>
        <Link href="/login" className="btn btn-primary">
          Pedir um novo link
        </Link>
      </div>
    );
  }

  const busy = phase === "busy";
  return (
    <div className="card auth-card" aria-busy={busy}>
      <p>Confirme para iniciar sessão neste dispositivo.</p>
      <button type="button" className="btn btn-primary btn-block" onClick={onEnter} disabled={busy} autoFocus>
        {busy ? "A entrar…" : "Entrar"}
      </button>
      <p role="status" aria-live="polite" className="status">
        {busy ? "A validar o link…" : ""}
      </p>
      <p role="alert" className="error">
        {phase === "failed" ? "Não foi possível iniciar sessão. Tente novamente." : ""}
      </p>
    </div>
  );
}
