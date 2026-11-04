import { describe, expect, it } from "vitest";
import { checkFile, declaredType } from "./file-checks";

describe("declaredType", () => {
  it.each([
    ["audio/mpeg", "a.mp3", "audio/mpeg"],
    ["audio/mp3", "a.mp3", "audio/mp3"],
    ["audio/x-flac", "a.flac", "audio/x-flac"],
    ["audio/vnd.wave", "a.wav", "audio/vnd.wave"],
    ["", "Riff.FLAC", "audio/flac"],
    ["", "a.ogg", "audio/ogg"],
    ["", "a.wav", "audio/wav"],
    ["", "a.mp3", "audio/mpeg"],
  ])("type %j name %j -> %j", (type, name, expected) => {
    expect(declaredType({ type, name })).toBe(expected);
  });

  it("returns empty when neither type nor extension is known", () => {
    expect(declaredType({ type: "", name: "notes.txt" })).toBe("");
  });
});

describe("checkFile accepts the server's aliases", () => {
  it.each(["audio/mp3", "audio/x-flac", "audio/vnd.wave", "audio/wave"])("%s", (type) => {
    expect(checkFile({ type, name: "x", size: 10 })).toBeNull();
  });

  it("accepts a known extension when the browser gives no type", () => {
    expect(checkFile({ type: "", name: "take1.flac", size: 10 })).toBeNull();
  });

  it("rejects an unknown extension with no type", () => {
    expect(checkFile({ type: "", name: "take1.txt", size: 10 })).toMatch(/Formato/);
  });
});
