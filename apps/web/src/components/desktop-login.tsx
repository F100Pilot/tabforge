"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { desktopLogin } from "@/lib/api";
import { tokenFromHash } from "@/lib/auth-ui";
import { DESKTOP_RESTART_MESSAGE, IS_DESKTOP } from "@/lib/desktop";
import { useSession } from "./session-provider";

/**
 * The launcher opens this page itself, so the token is used at once (no button: no email
 * scanners here). The token is removed from the address bar before the request.
 */
export function DesktopLogin() {
  const router = useRouter();
  const { refresh } = useSession();
  const [failed, setFailed] = useState(false);
  // Read once: effects can run twice in development, and the hash is cleared on first read.
  const tokenRef = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (tokenRef.current === undefined) {
      tokenRef.current = IS_DESKTOP ? tokenFromHash(window.location.hash) : null;
      window.history.replaceState(null, "", window.location.pathname);
    }
    const token = tokenRef.current;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      if (!token) {
        setFailed(true);
        return;
      }
      desktopLogin(token)
        .then(() => refresh())
        .then(() => {
          if (!cancelled) router.replace("/");
        })
        .catch(() => {
          if (!cancelled) setFailed(true);
        });
    });
    return () => {
      cancelled = true;
    };
  }, [refresh, router]);

  if (failed) {
    return (
      <p role="alert" className="error-text">
        {DESKTOP_RESTART_MESSAGE}
      </p>
    );
  }
  return (
    <p className="muted" role="status" aria-live="polite">
      A abrir o TabForge…
    </p>
  );
}
