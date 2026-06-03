import { cpSync, copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();
const DIST = join(ROOT, "dist");
const FILES = ["background.js", "content.js", "scraper.js", "overlay.css", "manifest.json"];

function ensureCleanDist() {
  rmSync(DIST, { recursive: true, force: true });
  mkdirSync(DIST, { recursive: true });
}

function copyFiles() {
  for (const file of FILES) {
    const src = join(ROOT, file);
    if (!existsSync(src)) {
      throw new Error(`Missing required file: ${file}`);
    }
    copyFileSync(src, join(DIST, file));
  }
}

function copyIcons() {
  const iconsSrc = join(ROOT, "icons");
  if (existsSync(iconsSrc)) {
    cpSync(iconsSrc, join(DIST, "icons"), { recursive: true });
  }
}

function main() {
  ensureCleanDist();

  if (process.argv.includes("--clean")) {
    console.log("dist cleaned");
    return;
  }

  copyFiles();
  copyIcons();
  console.log("dist created successfully");
}

main();
