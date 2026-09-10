// Playwright-substitute QA script: navigates every route at several viewport widths,
// captures console errors/pageerrors, and saves full-page screenshots for manual review.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.QA_BASE_URL ?? "http://localhost:3100";
const OUT_DIR = path.resolve(import.meta.dirname, "screenshots");
fs.mkdirSync(OUT_DIR, { recursive: true });

const ROUTES = [
  "/",
  "/live-detection",
  "/experiments",
  "/drift",
  "/synthetic-lab",
  "/fidelity-gate",
  "/adaptation",
  "/topology",
  "/audit-log",
  "/models",
];

const VIEWPORTS = [
  { name: "1920x1080", width: 1920, height: 1080 },
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "mobile-390x844", width: 390, height: 844 },
];

const browser = await chromium.launch();
let hadErrors = false;

for (const vp of VIEWPORTS) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
  for (const route of ROUTES) {
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(String(err)));

    const url = `${BASE}${route}`;
    try {
      await page.goto(url, { waitUntil: "networkidle", timeout: 20000 });
      await page.waitForTimeout(300);
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      const overflow = scrollWidth > clientWidth + 1;

      const fname = `${vp.name}__${route === "/" ? "overview" : route.replace(/\//g, "")}.png`;
      await page.screenshot({ path: path.join(OUT_DIR, fname), fullPage: true });

      const status = consoleErrors.length > 0 || overflow ? "ISSUES" : "OK";
      if (status === "ISSUES") hadErrors = true;
      console.log(
        `[${status}] ${vp.name} ${route} — consoleErrors=${consoleErrors.length} overflow=${overflow}${
          overflow ? ` (scrollWidth=${scrollWidth} clientWidth=${clientWidth})` : ""
        }`
      );
      for (const e of consoleErrors) console.log(`    console: ${e.slice(0, 300)}`);
    } catch (err) {
      hadErrors = true;
      console.log(`[FAIL] ${vp.name} ${route} — ${err}`);
    } finally {
      await page.close();
    }
  }
  await context.close();
}

await browser.close();
console.log(hadErrors ? "\nQA pass found issues — see above." : "\nQA pass clean.");
process.exit(hadErrors ? 1 : 0);
