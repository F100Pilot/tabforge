"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { completeUpload, createUpload, importYoutube, isUnauthenticated, putFile, type SourceKind } from "@/lib/api";
import { checkFile } from "@/lib/file-checks";
import { IS_DESKTOP } from "@/lib/desktop";
import { isYoutubeUrl, youtubeProblemMessage } from "@/lib/youtube";

type Phase = "idle" | "preparing" | "uploading" | "finishing" | "importing";

const PHASE_LABEL: Record<Phase, string> = {
  idle: "",
  preparing: "A preparar o envio…",
  uploading: "A enviar o ficheiro…",
  finishing: "A iniciar a transcrição…",
  importing: "A descarregar do YouTube e a converter para MP3…",
};

export function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<SourceKind>("guitar_stem");
  const [error, setError] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [link, setLink] = useState("");
  const busy = phase !== "idle";
  const fileInput = useRef<HTMLInputElement>(null);

  // Next keeps this page alive (hidden by React <Activity>, cacheComponents) after the
  // router.push to the job: without this reset, coming back showed the form still busy
  // ("A descarregar do YouTube…") with every control disabled. Each visit starts fresh.
  useLayoutEffect(() => {
    const input = fileInput.current;
    return () => {
      setPhase("idle");
      setFile(null);
      if (input) input.value = ""; // the DOM is kept too
      setLink("");
      setError(null);
      setNeedsLogin(false);
    };
  }, []);

  /** Desktop only (ADR-0014): the API downloads the MP3, keeps a copy and queues the job. */
  async function onImport() {
    if (!isYoutubeUrl(link)) {
      setError("Cole o link de um vídeo do YouTube.");
      return;
    }
    setError(null);
    setNeedsLogin(false);
    try {
      setPhase("importing");
      const result = await importYoutube(link, kind);
      router.push(`/jobs/${encodeURIComponent(result.job.id)}`);
    } catch (err) {
      setError(isUnauthenticated(err) ? "Inicie sessão para continuar." : youtubeProblemMessage(err));
      setNeedsLogin(isUnauthenticated(err));
      setPhase("idle");
    }
  }

  function onLinkKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault(); // Enter here imports the link instead of submitting the file form
      void onImport();
    }
  }

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
    setNeedsLogin(false);
    try {
      setPhase("preparing");
      const ticket = await createUpload(file, kind);
      setPhase("uploading");
      await putFile(ticket, file);
      setPhase("finishing");
      const job = await completeUpload(ticket.audio_id);
      router.push(`/jobs/${encodeURIComponent(job.id)}`);
    } catch (err) {
      setError(
        isUnauthenticated(err)
          ? "Inicie sessão para continuar."
          : err instanceof Error
            ? err.message
            : "Ocorreu um erro inesperado.",
      );
      setNeedsLogin(isUnauthenticated(err));
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
          ref={fileInput}
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

      {IS_DESKTOP && (
        <div className="yt-import">
          <label htmlFor="youtube-url">Ou cole um link do YouTube</label>
          <div className="yt-row">
            <input
              id="youtube-url"
              type="url"
              inputMode="url"
              placeholder="https://www.youtube.com/watch?v=…"
              value={link}
              disabled={busy}
              onChange={(e) => setLink(e.target.value)}
              onKeyDown={onLinkKey}
            />
            <button type="button" className="btn" disabled={busy || !link.trim()} onClick={() => void onImport()}>
              Importar
            </button>
          </div>
          <span className="yt-hint">Converte para MP3, guarda uma cópia em Música\TabForge e transcreve.</span>
        </div>
      )}

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

      <p className="note">
        {IS_DESKTOP ? "Fica só neste PC" : "Privado · o áudio é apagado ao fim de 30 dias"}
      </p>

      <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
        Gerar tablatura
      </button>

      <p role="status" aria-live="polite" className="status">
        {PHASE_LABEL[phase]}
      </p>
      <p role="alert" className="error">
        {error}
      </p>
      {needsLogin && (
        <Link href="/login" className="btn btn-primary btn-block">
          Iniciar sessão
        </Link>
      )}
    </form>
  );
}
