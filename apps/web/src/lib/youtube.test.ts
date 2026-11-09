import { describe, expect, it } from "vitest";
import { ProblemError } from "./api";
import { isYoutubeUrl, youtubeProblemMessage } from "./youtube";

describe("isYoutubeUrl (same rule as the API)", () => {
  it.each([
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
    "  https://m.youtube.com/watch?v=dQw4w9WgXcQ  ",
  ])("accepts %s", (url) => expect(isYoutubeUrl(url)).toBe(true));
  it.each([
    "",
    "youtube",
    "https://www.youtube.com.evil.example/watch?v=x",
    "https://user@www.youtube.com/watch?v=x",
    "https://www.youtube.com:8443/watch?v=x",
    "ftp://www.youtube.com/x",
  ])("refuses %s", (url) => expect(isYoutubeUrl(url)).toBe(false));
});

describe("youtubeProblemMessage", () => {
  const p = (status: number, code: string, detail = "d") => new ProblemError({ status, code, title: "", detail });
  it("explains each failure in Portuguese", () => {
    expect(youtubeProblemMessage(p(422, "invalid_youtube_url"))).toMatch(/link de um vídeo do YouTube/);
    expect(youtubeProblemMessage(p(422, "audio_too_long"))).toMatch(/mais de 10 minutos/);
    expect(youtubeProblemMessage(p(502, "download_failed", "Video unavailable"))).toBe(
      "Não foi possível descarregar do YouTube: Video unavailable",
    );
    expect(youtubeProblemMessage(p(501, "unavailable"))).toMatch(/start\.bat/);
    expect(youtubeProblemMessage(p(413, "file_too_large"))).toMatch(/50 MB/);
    expect(youtubeProblemMessage(new Error("x"))).toBe("Não foi possível importar do YouTube.");
  });
});
