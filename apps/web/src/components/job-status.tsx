"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getJob, type Job, type JobStage, type JobStatus } from "@/lib/api";

const POLL_MS = 2000;

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Na fila de espera",
  running: "Em processamento",
  done: "Concluído",
  failed: "Falhou",
};
const STAGE_LABEL: Record<JobStage, string> = {
  separating: "A separar a guitarra do resto da música",
  transcribing: "A transcrever as notas",
  arranging: "A arranjar a tablatura",
};

export function JobStatusView({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="stack">
      <div role="status" aria-live="polite" className="status">
        {job ? (
          <>
            <p>
              Estado: <strong>{STATUS_LABEL[job.status]}</strong>
            </p>
            {job.status === "running" && job.stage && <p>{STAGE_LABEL[job.stage]}…</p>}
            {job.status === "done" && <p>A abrir a tablatura…</p>}
            {job.status === "failed" && (
              <p className="error">
                A transcrição falhou (código: <code>{job.error_code ?? "desconhecido"}</code>).
              </p>
            )}
          </>
        ) : (
          <p>A carregar o estado…</p>
        )}
      </div>
      <p role="alert" className="error">
        {error}
      </p>
      {job?.status === "failed" && <Link href="/">Tentar com outro ficheiro</Link>}
    </div>
  );
}
