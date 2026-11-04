"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listJobs, type JobSummary } from "@/lib/api";
import { formatDuration, relativeTime } from "@/lib/format";
import { jobHref, jobTitle, statusView } from "@/lib/job-view";

export function RecentJobs() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    listJobs(5, ctrl.signal)
      .then((j) => {
        setJobs(j);
        setNow(Date.now());
      })
      .catch(() => {
        if (!ctrl.signal.aborted) setFailed(true);
      });
    return () => ctrl.abort();
  }, []);

  return (
    <section aria-labelledby="recent-h" className="recent">
      <h2 id="recent-h">Recentes</h2>
      {failed ? (
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
              <li key={j.id}>
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
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
