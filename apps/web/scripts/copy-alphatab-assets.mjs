// Copies alphaTab runtime assets (scripts, music font, soundfont) into public/alphatab/.
// Turbopack bundles no workers/worklets for alphaTab, so they are served statically.
import { cpSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const dist = dirname(require.resolve("@coderline/alphatab")); // main entry lives in dist/
const out = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "alphatab");

rmSync(out, { recursive: true, force: true });
mkdirSync(join(out, "font"), { recursive: true });
mkdirSync(join(out, "soundfont"), { recursive: true });
for (const f of ["alphaTab.mjs", "alphaTab.core.mjs", "alphaTab.worker.mjs", "alphaTab.worklet.mjs"]) {
  cpSync(join(dist, f), join(out, f));
}
for (const f of ["Bravura.woff2", "Bravura.woff", "Bravura.otf", "Bravura-OFL.txt"]) {
  cpSync(join(dist, "font", f), join(out, "font", f));
}
cpSync(join(dist, "soundfont", "sonivox.sf2"), join(out, "soundfont", "sonivox.sf2"));
cpSync(join(dist, "soundfont", "LICENSE"), join(out, "soundfont", "LICENSE"));
if (!existsSync(join(out, "soundfont", "sonivox.sf2"))) throw new Error("asset copy failed");
console.log("alphaTab assets copied to public/alphatab");
