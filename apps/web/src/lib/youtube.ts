/** YouTube import (desktop only, ADR-0014): the link check mirrors the API's `is_youtube_url`. */
import { ProblemError } from "./api";

const HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"]);
const MAX_URL_LENGTH = 2048;

export function isYoutubeUrl(text: string): boolean {
  const value = text.trim();
  if (!value || value.length > MAX_URL_LENGTH) return false;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  return (
    (url.protocol === "https:" || url.protocol === "http:") &&
    HOSTS.has(url.hostname) &&
    url.username === "" &&
    url.password === "" &&
    url.port === ""
  );
}

export function youtubeProblemMessage(err: unknown): string {
  if (err instanceof ProblemError) {
    switch (err.code) {
      case "invalid_youtube_url":
        return "Cole o link de um vídeo do YouTube.";
      case "audio_too_long":
        return "O vídeo tem mais de 10 minutos.";
      case "download_failed":
        return `Não foi possível descarregar do YouTube: ${err.message}`;
      case "unavailable":
        return "A importação do YouTube não está instalada. Feche o TabForge e corra o start.bat outra vez.";
      case "file_too_large":
        return "O áudio tem mais de 50 MB.";
    }
    return err.message;
  }
  return "Não foi possível importar do YouTube.";
}
