/**
 * README screenshot capture. Not part of the build -- a dev tool that drives the running
 * app through the real workflow and writes the images the root README embeds.
 *
 *   node scripts/readme-shots.mjs [--base http://127.0.0.1:3000] [--out ../docs/readme]
 *
 * The backend must be up (DEMO_REPLAY is enough) or the evidence shots will capture the
 * API-unavailable state instead of a result.
 */
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const argv = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = argv.indexOf("--" + name);
  return i === -1 ? fallback : argv[i + 1];
};

const BASE = flag("base", "http://127.0.0.1:3000");
const OUT = path.resolve(flag("out", "../docs/readme"));
const WIDTH = 1440;

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: WIDTH, height: 900 },
  // 1x on purpose. GitHub renders README images around 880px wide, so 1440 is already
  // oversampled, and a retina capture would triple what the repository has to carry.
  deviceScaleFactor: 1,
  // The follower aura and entry animations are decorative. Freezing them keeps captures
  // reproducible and keeps a half-faded section out of a documentation image.
  reducedMotion: "reduce",
});
const page = await context.newPage();
const problems = [];
page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));

/** Walk the page so IntersectionObserver-driven sections finish entering. */
async function settle() {
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.7;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 80));
    }
    window.scrollTo(0, 0);
    await new Promise((r) => setTimeout(r, 200));
  });
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(350);
}

async function shoot(name, target) {
  const file = path.join(OUT, name + ".png");
  if (target) await target.screenshot({ path: file });
  else await page.screenshot({ path: file });
  console.log("shot", name);
}

async function go(route) {
  await page.goto(BASE + route, { waitUntil: "networkidle" });
  await settle();
}

// ---------------------------------------------------------------- marketing surfaces
await go("/");
await shoot("shot-home");

await go("/platform");
await shoot("shot-platform");

await go("/proof");
await shoot("shot-proof");

// ------------------------------------------------------------------ the three cases
await go("/demo/kichler");
await shoot("shot-demo-kichler");

// The evidence comparison is the point of the Kichler page: proposal beside the source
// line it was checked against, including the ones that did not survive.
const evidence = page.locator("text=3-Light").first();
if (await evidence.count()) {
  await evidence.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await shoot("shot-kichler-withheld");
}

await go("/demo/satco");
await shoot("shot-demo-satco");

await go("/demo/feit");
await shoot("shot-demo-feit");

// --------------------------------------------------------------------- the Workbench
await go("/workbench");
await shoot("shot-workbench-upload");

// Load the committed sample catalog through the real import path.
await page.getByRole("button", { name: /try the sample catalog/i }).click();
await page.waitForTimeout(900);
await settle();
await shoot("shot-workbench-schema");

// Schema review -> catalog grid.
await page.getByRole("button", { name: "Prepare catalog" }).click();
await page.waitForTimeout(700);
await settle();
await shoot("shot-workbench-catalog");

// Analyze the Kichler row. Its table row carries the "Full replay available" badge, and
// it is the only one of the four sample rows that reaches verified facts.
await page.getByRole("row", { name: /45297BK/ }).getByRole("button", { name: "Analyze" }).click();
await page.waitForTimeout(2500);
await page.locator("#results").scrollIntoViewIfNeeded();
await page.waitForTimeout(600);
await shoot("shot-workbench-result");

// The withheld tab is where the refusals are legible.
const withheldTab = page.getByRole("tab", { name: "Withheld" });
if (await withheldTab.count()) {
  await withheldTab.click();
  await page.waitForTimeout(500);
  await page.locator("#results").scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await shoot("shot-workbench-withheld");
}

await browser.close();

if (problems.length) {
  console.log("\nPROBLEMS:");
  for (const problem of problems) console.log(" -", problem);
  process.exitCode = 1;
} else {
  console.log("\ncaptured cleanly");
}
