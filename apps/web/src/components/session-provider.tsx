"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getSession, type SessionUser } from "@/lib/api";

export type SessionStatus = "loading" | "anonymous" | "authenticated";

interface SessionValue {
  status: SessionStatus;
  user: SessionUser | null;
  /** Re-reads the session from the API (after login, logout or account deletion). */
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ status: SessionStatus; user: SessionUser | null }>({
    status: "loading",
    user: null,
  });

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const s = await getSession(signal);
      if (signal?.aborted) return;
      setState(s ? { status: "authenticated", user: s.user } : { status: "anonymous", user: null });
    } catch {
      // API unreachable: treat as anonymous so the UI stays usable; pages show their own errors.
      if (!signal?.aborted) setState({ status: "anonymous", user: null });
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    queueMicrotask(() => void load(ctrl.signal));
    return () => ctrl.abort();
  }, [load]);

  const refresh = useCallback(() => load(), [load]);
  const value = useMemo<SessionValue>(() => ({ ...state, refresh }), [state, refresh]);
  return <SessionContext value={value}>{children}</SessionContext>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}
