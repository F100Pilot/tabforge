"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getJob, listJobs, type Job, type SourceKind } from "@/lib/api";
import { errorMessage, STEPS, stepHint, stepStates } from "@/lib/job-view";

const POLL_MS = 2000;

export function JobStatusView({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [sourceKind, setSourceKind] = useState<SourceKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  // source_kind is only exposed by the list endpoint; best effort, once.
  useEffect(() => {
    const ctrl = new AbortController();
    listJobs(100, ctrl.signal)
      .then((items) => {
        const found = items.find((i) => i.id === jobId);
        if (found) setSourceKind(found.source_kind);
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, [jobId]);

  useEffect(() => {
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const j = await getJob(jobId, ctrl.signal);
        if (ctrl.signal.aborted) return;
        setJob(j);
        setError(null);
        if (j.status === "done" && j.tab_id) {
          router.replace(`/tabs/${encodeURIComponent(j.tab_id)}`);
          return;
        }
        if (j.status === "failed") return;
      } catch (err) {
        if (ctrl.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Erro ao consultar o estado.");
      }
      timer = setTimeout(poll, POLL_MS);
    }
    void poll();

    return () => {
      ctrl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [jobId, router]);

  if (job?.status === "failed") {
    return (
      <div className="card center-card" role="alert">
        <h1>Não foi possível gerar a tablatura</h1>
        <p className="error-text">{errorMessage(job.error_code)}</p>
        <Link href="/" className="btn btn-primary">
          Carregar outro ficheiro
        </Link>
      </div>
    );
  }

  const states = job ? stepStates(job.status, job.stage, sourceKind) : null;

  return (
    <div className="card center-card">
      <h1>A processar a gravação</h1>
      <div role="status" aria-live="polite">
        {job ? (
          <p className="muted">
            {job.status === "queued" ? "Em fila" : job.status === "done" ? "A abrir a tablatura…" : "Em processamento"}
          </p>
        ) : (
          <p className="muted">A carregar o estado…</p>
        )}
      </div>
      <ol className="stepper" aria-label="Progresso">
        {STEPS.map((step, i) => {
          const st = states?.[i] ?? "pending";
          return (
            <li key={step.stage} className={`step step-${st}`} aria-current={st === "current" ? "step" : undefined}>
              <span className="step-marker" aria-hidden="true">
                {st === "done" ? "✓" : st === "skipped" ? "–" : i + 1}
              </span>
              <span className="step-label">{step.label}</span>
              <span className="step-hint">{stepHint(i, st, sourceKind)}</span>
              <span className="sr-only">
                {st === "done" ? " (concluído)" : st === "current" ? " (em curso)" : st === "skipped" ? " (saltado)" : ""}
              </span>
              {st === "current" && <span className="bar" aria-hidden="true"><span /></span>}
            </li>
          );
        })}
      </ol>
      <p className="note">Pode sair desta página: a tab aparece em As minhas tabs quando estiver pronta.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
