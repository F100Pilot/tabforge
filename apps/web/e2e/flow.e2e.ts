import { readFileSync } from "node:fs";
import type { Download } from "@playwright/test";
import { expect, test, type Page } from "@playwright/test";

/*
 * Whole user journey on the stub pipeline: email-link login, upload, tab, edit + save,
 * logout, account deletion. The API runs without SMTP in env=dev, so the login email is
 * written to its log (E2E_API_LOG); the test reads the newest link from there.
 */

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";
const API_LOG = process.env.E2E_API_LOG;
const LINK = /https?:\/\/[^\s]+\/login\/verify#token=[\w-]+/g;

function newestLink(): string | null {
  if (!API_LOG) throw new Error("E2E_API_LOG must point at the API log file");
  const links = readFileSync(API_LOG, "utf8").match(LINK);
  return links ? links[links.length - 1] : null;
}

/** 1 s of 16-bit mono silence at 22.05 kHz: a valid WAV for the stub pipeline. */
function silentWav(): Buffer {
  const rate = 22050;
  const data = Buffer.alloc(rate * 2);
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20); // PCM
  header.writeUInt16LE(1, 22); // mono
  header.writeUInt32LE(rate, 24);
  header.writeUInt32LE(rate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(data.length, 40);
  return Buffer.concat([header, data]);
}

async function sessionStatus(page: Page): Promise<number> {
  return page.evaluate(
    (api) => fetch(`${api}/v1/auth/session`, { credentials: "include" }).then((r) => r.status),
    API_URL,
  );
}

async function signIn(page: Page, email: string): Promise<string> {
  const before = newestLink();
  await page.goto("/login");
  await page.locator("#login-email").fill(email);
  await page.locator("button[type=submit]").click();
  await expect(page.getByText(/Enviámos um link/)).toBeVisible();
  await expect.poll(newestLink).not.toBe(before);
  const link = newestLink()!;
  await page.goto(link);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL("/");
  await expect(page.getByText(email).first()).toBeVisible();
  expect(page.url()).not.toContain("token");
  return link;
}

async function downloadBytes(download: Download): Promise<Buffer> {
  const path = await download.path();
  return readFileSync(path);
}

async function selectFirstNote(page: Page): Promise<void> {
  const frets = page.locator(".at-host svg text").filter({ hasText: /^\d+$/ });
  await expect(frets.first()).toBeVisible({ timeout: 30_000 });
  const inspector = page.getByRole("dialog");
  // alphaTab handles clicks on its surface, so click the glyph's position.
  for (let i = 0, n = await frets.count(); i < n && !(await inspector.isVisible()); i++) {
    const box = await frets.nth(i).boundingBox();
    if (box) await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(150);
  }
  await expect(inspector).toBeVisible();
}

test("sign in, transcribe, edit, sign out and delete the account", async ({ page, context }) => {
  const email = `e2e+${Date.now()}@example.com`;

  await page.goto("/tabs");
  await expect(page.getByText(/Inicie sessão para continuar/)).toBeVisible();
  expect(await sessionStatus(page)).toBe(401);

  const link = await signIn(page, email);
  expect(await sessionStatus(page)).toBe(200);

  const other = await context.newPage();
  await other.goto(link);
  await other.getByRole("button", { name: "Entrar" }).click();
  await expect(other.getByText(/expirou ou já foi usado/)).toBeVisible();
  await other.close();

  await page.goto("/");
  await page.setInputFiles("#audio-file", { name: "silence.wav", mimeType: "audio/wav", buffer: silentWav() });
  await page.getByRole("button", { name: /Gerar tablatura/ }).click();
  await page.waitForURL(/\/tabs\/[0-9a-f-]{36}$/, { timeout: 60_000 });
  const tabUrl = page.url();

  await page.goto(`${tabUrl}/edit`);
  await selectFirstNote(page);
  await page.keyboard.press("5");
  await expect(page.getByText("Por guardar")).toBeVisible();
  await page.keyboard.press("Control+s");
  await expect(page.getByText("Revisão guardada.")).toBeVisible();

  // US-05: Guitar Pro and MIDI downloads, and printing on the light palette.
  await page.goto(tabUrl);
  await expect(page.getByText("Pronto.")).toBeVisible({ timeout: 30_000 });
  for (const [label, ext, magic] of [
    ["Guitar Pro", ".gp", "PK"],
    ["MIDI", ".mid", "MThd"],
  ] as const) {
    await page.getByRole("button", { name: /Exportar/ }).click();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      // Scoped to the export menu: the comparison card also has "Guitar Pro" buttons.
      page.locator("#export-menu").getByRole("button", { name: new RegExp(label) }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(new RegExp(`\\${ext}$`));
    expect((await downloadBytes(download)).subarray(0, magic.length).toString("latin1")).toBe(magic);
  }
  await page.getByRole("button", { name: "Escura" }).click();
  await page.evaluate(() => {
    const w = window as unknown as { printedTheme?: string | null };
    window.print = () => {
      w.printedTheme = document.querySelector("[data-score-theme]")?.getAttribute("data-score-theme") ?? null;
    };
  });
  await page.getByRole("button", { name: /Exportar/ }).click();
  await page.locator("#export-menu").getByRole("button", { name: "Imprimir / PDF" }).click();
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { printedTheme?: string }).printedTheme))
    .toBe("light");
  await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
  await expect(page.locator("[data-score-theme]")).toHaveAttribute("data-score-theme", "dark");

  await page.goto("/");
  await page.getByRole("button", { name: "Terminar sessão" }).click();
  await expect(page.getByRole("link", { name: "Iniciar sessão" }).first()).toBeVisible();
  expect(await sessionStatus(page)).toBe(401);

  await signIn(page, email);
  await page.goto("/conta");
  await page.locator("#confirm-email").fill(email.toUpperCase());
  await page.locator(".danger-zone button[type=submit]").click();
  await page.waitForURL(/aviso=conta-eliminada/);
  expect(await sessionStatus(page)).toBe(401);

  // The deleted account's tab is gone for good: signing in again with the same email starts empty.
  await signIn(page, email);
  await page.goto(tabUrl);
  await expect(page.getByRole("alert")).toBeVisible();
});
