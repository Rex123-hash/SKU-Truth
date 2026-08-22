/**
 * Render the README's SVG assets to PNG so they can be eyeballed the way GitHub will
 * show them: as flat images, with no external fonts and no page CSS to lean on.
 *
 *   node scripts/render-svg.mjs ../docs/readme/hero.svg [more.svg ...]
 *
 * Writes <name>.preview.png beside a temp dir, not into docs/. This is a proofing tool.
 */
import { chromium } from "playwright";
import { readFile, mkdir } from "node:fs/promises";
import path from "node:path";

const argv = process.argv.slice(2);
const outIndex = argv.indexOf("--out");
const OUT = path.resolve(outIndex === -1 ? "svg-preview" : argv[outIndex + 1]);
const files = argv.filter((arg, i) => arg.endsWith(".svg") && argv[i - 1] !== "--out");
await mkdir(OUT, { recursive: true });

const browser = await chromium.launch();

for (const file of files) {
  const abs = path.resolve(file);
  const svg = await readFile(abs, "utf8");
  const width = Number(/viewBox="0 0 (\d+(?:\.\d+)?) /.exec(svg)?.[1] ?? 1200);
  const height = Number(/viewBox="0 0 \d+(?:\.\d+)? (\d+(?:\.\d+)?)"/.exec(svg)?.[1] ?? 600);

  const page = await browser.newPage({
    viewport: { width: Math.ceil(width), height: Math.ceil(height) },
    deviceScaleFactor: 1,
  });
  // Loaded through an <img> on purpose: that is the element GitHub uses, and it is the
  // strictest context -- no scripts, no external resources, no inherited page styles.
  await page.setContent(
    `<body style="margin:0;background:#fff"><img src="data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}" width="${width}" height="${height}"></body>`,
  );
  await page.waitForTimeout(250);
  const name = path.basename(abs, ".svg") + ".preview.png";
  await page.screenshot({ path: path.join(OUT, name) });
  console.log("rendered", name, `${width}x${height}`);
  await page.close();
}

await browser.close();
