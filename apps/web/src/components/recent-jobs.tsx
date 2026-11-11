"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { deleteJob, isUnauthenticated, listJobs, type JobSummary } from "@/lib/api";
import { formatDuration, relativeTime } from "@/lib/format";
import { jobHref, jobTitle, statusView } from "@/lib/job-view";
import { DeleteSong } from "./delete-song";

export function RecentJobs() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [now, setNow] = useState<number | null>(null);
  // A list fetched before a delete finished must not bring the deleted song back.
  const deleted = useRef(new Set<string>());

  useEffect(() => {
    const ctrl = new AbortController();
    listJobs(5, ctrl.signal)
      .then((j) => {
        setJobs(j.filter((x) => !deleted.current.has(x.id)));
        setNow(Date.now());
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        if (isUnauthenticated(err)) setNeedsLogin(true);
        else setFailed(true);
      });
    return () => ctrl.abort();
  }, []);

  return (
    <section aria-labelledby="recent-h" className="recent">
      <h2 id="recent-h">Recentes</h2>
      {needsLogin ? (
        <p className="muted">
          <Link href="/login">Inicie sessão</Link> para continuar.
        </p>
      ) : failed ? (
        <p className="muted">Não foi possível carregar as tabs recentes.</p>
      ) : !jobs ? (
        <p className="muted" role="status">A carregar…</p>
      ) : jobs.length === 0 ? (
        <p className="muted">Ainda não carregou nenhuma gravação.</p>
      ) : (
        <ul className="cards">
          {jobs.map((j) => {
            const st = statusView(j.status);
            return (
              <li key={j.id} className="song">
                <Link href={jobHref(j)} className="card-link">
                  <span className="card-title">{jobTitle(j)}</span>
                  <span className="card-meta">
                    <span className={`tone tone-${st.tone}`}>
                      <span className="dot" aria-hidden="true" />
                      {st.label}
                    </span>
                    {now !== null && <span>{relativeTime(j.created_at, now)}</span>}
                    {j.duration_ms !== null && <span className="mono">{formatDuration(j.duration_ms)}</span>}
                  </span>
                </Link>
                {j.status !== "running" && (
                  <DeleteSong
                    title={jobTitle(j)}
                    onDelete={async () => {
                      await deleteJob(j.id);
                      deleted.current.add(j.id);
                      setJobs((list) => list?.filter((x) => x.id !== j.id) ?? null);
                    }}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
