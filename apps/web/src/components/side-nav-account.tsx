"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { logout } from "@/lib/api";
import { useSession } from "./session-provider";

export function SideNavAccount() {
  const { status, user, refresh } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  if (status === "loading") return <div className="account" aria-hidden="true" />;
  if (status === "anonymous" || !user) {
    return (
      <div className="account">
        <Link href="/login" className="navlink">
          Iniciar sessão
        </Link>
      </div>
    );
  }

  async function onLogout() {
    setBusy(true);
    try {
      await logout();
    } catch {
      // Even if the call failed, re-read the real state below.
    }
    await refresh();
    setBusy(false);
    router.replace("/");
  }

  return (
    <div className="account">
      <Link href="/conta" className="account-email" title="Conta">
        {user.email}
      </Link>
      <button type="button" className="btn btn-small" onClick={onLogout} disabled={busy}>
        Terminar sessão
      </button>
    </div>
  );
}
