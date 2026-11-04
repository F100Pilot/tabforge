import { describe, expect, it } from "vitest";
import { ConfigError, parsePublicConfig } from "./config";

describe("parsePublicConfig", () => {
  it("parses a valid URL", () => {
    const cfg = parsePublicConfig({ NEXT_PUBLIC_API_URL: "http://localhost:8000" });
    expect(cfg.apiBaseUrl.host).toBe("localhost:8000");
  });

  it.each([
    [undefined, "required"],
    ["", "required"],
    ["not-a-url", "absolute URL"],
    ["ftp://x.y", "http or https"],
  ])("rejects %s", (value, message) => {
    expect(() => parsePublicConfig({ NEXT_PUBLIC_API_URL: value })).toThrow(ConfigError);
    expect(() => parsePublicConfig({ NEXT_PUBLIC_API_URL: value })).toThrow(message);
  });
});
