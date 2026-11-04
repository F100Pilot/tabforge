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
  const [dragging, setDragging] = useState(false);
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

  function pick(f: File | null) {
    setFile(f);
    setError(f ? checkFile(f) : null);
  }

  return (
    <form onSubmit={onSubmit} aria-busy={busy} className="card upload">
      <label
        htmlFor="audio-file"
        className={`dropzone${dragging ? " dragging" : ""}${busy ? " disabled" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!busy) pick(e.dataTransfer.files?.[0] ?? null);
        }}
      >
        <input
          id="audio-file"
          className="sr-input"
          type="file"
          accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/flac,audio/x-flac,audio/ogg,.mp3,.wav,.flac,.ogg"
          disabled={busy}
          onChange={(e) => pick(e.target.files?.[0] ?? null)}
        />
        <span className="dz-title">
          {file ? file.name : "Largue o ficheiro aqui ou clique para escolher"}
        </span>
        <span className="chips">
          <span className="chip">MP3 · WAV · FLAC · OGG</span>
          <span className="chip">até 50 MB</span>
          <span className="chip">até 10 min</span>
        </span>
      </label>

      <fieldset disabled={busy} className="segmented">
        <legend>Tipo de gravação</legend>
        <label className="seg">
          <input
            type="radio"
            name="source_kind"
            value="guitar_stem"
            checked={kind === "guitar_stem"}
            onChange={() => setKind("guitar_stem")}
          />
          <span className="seg-body">
            <strong>Só a guitarra</strong>
            <span>Recomendado · mais rápido e fiel</span>
          </span>
        </label>
        <label className="seg">
          <input
            type="radio"
            name="source_kind"
            value="mix"
            checked={kind === "mix"}
            onChange={() => setKind("mix")}
          />
          <span className="seg-body">
            <strong>Guitarra com banda</strong>
            <span>Isolamos a guitarra · em avaliação</span>
          </span>
        </label>
      </fieldset>

      <p className="note">Privado · o áudio é apagado ao fim de 30 dias</p>

      <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
        Gerar tablatura
      </button>

      <p role="status" aria-live="polite" className="status">
        {PHASE_LABEL[phase]}
      </p>
      <p role="alert" className="error">
        {error}
      </p>
    </form>
  );
}
