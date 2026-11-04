import { describe, expect, it } from "vitest";
import { ProblemError } from "./api";
import {
  deleteAccountErrorMessage,
  emailMatches,
  magicLinkErrorMessage,
  tokenFromHash,
  verifyErrorKind,
} from "./auth-ui";

const problem = (status: number, code = "x") => new ProblemError({ status, code, title: "", detail: "d" });

describe("tokenFromHash", () => {
  it("reads the token", () => expect(tokenFromHash("#token=abc-123_x")).toBe("abc-123_x"));
  it("returns null when missing or empty", () => {
    expect(tokenFromHash("")).toBeNull();
    expect(tokenFromHash("#")).toBeNull();
    expect(tokenFromHash("#token=")).toBeNull();
    expect(tokenFromHash("#other=1")).toBeNull();
  });
  it("ignores other params", () => expect(tokenFromHash("#a=1&token=t")).toBe("t"));
});

describe("emailMatches", () => {
  it("ignores case and spaces", () => expect(emailMatches(" Ana@Mail.pt ", "ana@mail.pt")).toBe(true));
  it("rejects different or empty", () => {
    expect(emailMatches("ana@mail.pt", "bia@mail.pt")).toBe(false);
    expect(emailMatches("", "")).toBe(false);
  });
});

describe("messages", () => {
  it("maps magic-link errors", () => {
    expect(magicLinkErrorMessage(problem(422))).toContain("válido");
    expect(magicLinkErrorMessage(problem(429))).toContain("Demasiados");
    expect(magicLinkErrorMessage(new Error("x"))).toContain("Não foi possível");
  });
  it("maps delete errors", () => {
    expect(deleteAccountErrorMessage(problem(503))).toContain("indisponível");
    expect(deleteAccountErrorMessage(problem(500))).toContain("Não foi possível");
  });
  it("classifies verify errors", () => {
    expect(verifyErrorKind(problem(400, "invalid_token"))).toBe("invalid");
    expect(verifyErrorKind(problem(500))).toBe("failed");
  });
});
