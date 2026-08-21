/**
 * Visual QA capture. Not part of the build -- a dev tool for comparing the running site
 * against the approved mockups at the widths the design has to hold at.
 *
 *   node scripts/shoot.mjs [routes...] --widths 1440,390 --out ../shots
 */
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const argv = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = argv.indexOf("--" + name);
  return i === -1 ? fallback : argv[i + 1];
};
const positional = argv.filter((a, i) => !a.startsWith("--") && !argv[i - 1]?.startsWith("--"));

const BASE = flag("base", "http://127.0.0.1:3000");
const OUT = path.resolve(flag("out", "shots"));
const WIDTHS = flag("widths", "1440").split(",").map(Number);
const ROUTES = positional.length ? positional : ["/"];

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch();
const problems = [];

for (const width of WIDTHS) {
  const context = await browser.newContext({
    viewport: { width, height: 1000 },
    deviceScaleFactor: 1,
    // Motion is decorative here; freezing it keeps captures comparable run to run.
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(`[${width}] console: ${msg.text()}`);
  });
  page.on("pageerror", (err) => problems.push(`[${width}] pageerror: ${err.message}`));

  for (const route of ROUTES) {
    await page.goto(BASE + route, { waitUntil: "networkidle" });

    // Entry animations are driven by IntersectionObserver, and a full-page screenshot
    // does not scroll, so without this pass every below-fold section would be captured
    // at its initial opacity. Walk the page down, then return to the top.
    await page.evaluate(async () => {
      const step = window.innerHeight * 0.7;
      for (let y = 0; y < document.body.scrollHeight; y += step) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 90));
      }
      window.scrollTo(0, 0);
      await new Promise((r) => setTimeout(r, 250));
    });
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    if (overflow > 1) problems.push(`[${width}] ${route}: horizontal overflow of ${overflow}px`);

    const name = (route === "/" ? "home" : route.replace(/^\//, "").replace(/\//g, "-")) +
      `@${width}.png`;
    await page.screenshot({ path: path.join(OUT, name), fullPage: true });
    console.log("shot", name);
  }
  await context.close();
}

await browser.close();

if (problems.length) {
  console.log("\nPROBLEMS:");
  for (const problem of problems) console.log(" -", problem);
  process.exitCode = 1;
} else {
  console.log("\nno console errors, no horizontal overflow");
}
