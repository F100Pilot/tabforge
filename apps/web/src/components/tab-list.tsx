"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { deleteTab, isUnauthenticated, listTabs, type TabSummary } from "@/lib/api";
import { DeleteSong } from "./delete-song";
import { SignInPrompt } from "./sign-in-prompt";
import { formatDate } from "@/lib/format";

export function TabList() {
  const [tabs, setTabs] = useState<TabSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  // A list fetched before a delete finished must not bring the deleted song back.
  const deleted = useRef(new Set<string>());

  useEffect(() => {
    const ctrl = new AbortController();
    listTabs(100, ctrl.signal)
      .then((list) => setTabs(list.filter((x) => !deleted.current.has(x.id))))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        if (isUnauthenticated(err)) setNeedsLogin(true);
        else setError(err instanceof Error ? err.message : "Erro ao carregar as tabs.");
      });
    return () => ctrl.abort();
  }, []);

  if (needsLogin) return <SignInPrompt />;
  if (error) return <p role="alert" className="error">{error}</p>;
  if (!tabs) return <p className="muted" role="status">A carregar…</p>;
  if (tabs.length === 0) {
    return (
      <div className="card empty">
        <p>Ainda não tem tabs.</p>
        <Link href="/" className="btn btn-primary">
          Criar a primeira tablatura
        </Link>
      </div>
    );
  }
  return (
    <ul className="tab-grid">
      {tabs.map((t) => (
        <li key={t.id} className="song">
          <Link href={`/tabs/${encodeURIComponent(t.id)}`} className="card-link">
            <span className="card-title">{t.title}</span>
            <span className="card-meta">
              <span>{formatDate(t.created_at)}</span>
              <span className="chip">{t.visibility === "private" ? "Privada" : t.visibility}</span>
            </span>
          </Link>
          <DeleteSong
            title={t.title}
            onDelete={async () => {
              await deleteTab(t.id);
              deleted.current.add(t.id);
              setTabs((list) => list?.filter((x) => x.id !== t.id) ?? null);
            }}
          />
        </li>
      ))}
    </ul>
  );
}
