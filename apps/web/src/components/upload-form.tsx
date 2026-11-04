"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { completeUpload, createUpload, putFile, type SourceKind } from "@/lib/api";
import { checkFile } from "@/lib/file-checks";

type Phase = "idle" | "preparing" | "uploading" | "finishing";

const PHASE_LABEL: Record<Phase, string> = {
  idle: "",
  preparing: "A preparar o envio…",
  uploading: "A enviar o ficheiro…",
  finishing: "A iniciar a transcrição…",
};

export function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<SourceKind>("guitar_stem");
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const busy = phase !== "idle";

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!file) {
      setError("Escolha um ficheiro de áudio.");
      return;
    }
    const problem = checkFile(file);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    try {
      setPhase("preparing");
      const ticket = await createUpload(file, kind);
      setPhase("uploading");
      await putFile(ticket, file);
      setPhase("finishing");
      const job = await completeUpload(ticket.audio_id);
      router.push(`/jobs/${encodeURIComponent(job.id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ocorreu um erro inesperado.");
      setPhase("idle");
    }
  }

  return (
    <form onSubmit={onSubmit} aria-busy={busy} className="stack">
      <div className="field">
        <label htmlFor="audio-file">Ficheiro de áudio (MP3, WAV, FLAC ou OGG, até 50 MiB)</label>
        <input
          id="audio-file"
          type="file"
          accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/flac,audio/x-flac,audio/ogg,.mp3,.wav,.flac,.ogg"
          disabled={busy}
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setFile(f);
            setError(f ? checkFile(f) : null);
          }}
        />
      </div>

      <fieldset disabled={busy}>
        <legend>Tipo de gravação</legend>
        <label className="radio">
          <input
            type="radio"
            name="source_kind"
            value="guitar_stem"
            checked={kind === "guitar_stem"}
            onChange={() => setKind("guitar_stem")}
          />
          Guitarra isolada
        </label>
        <label className="radio">
          <input
            type="radio"
            name="source_kind"
            value="mix"
            checked={kind === "mix"}
            onChange={() => setKind("mix")}
          />
          Mistura com banda
        </label>
      </fieldset>

      <button type="submit" disabled={busy}>
        Gerar tablatura
      </button>

      <p role="status" aria-live="polite" className="status">
        {PHASE_LABEL[phase]}
      </p>
      <p role="alert" className="error">
        {error}
      </p>

      <p className="note">
        Os seus ficheiros são privados: as tabs são privadas por defeito.
      </p>
    </form>
  );
}
