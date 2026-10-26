/**
 * Curated README screenshots and tour frames from a freshly seeded stack.
 *
 *   make up && make demo
 *   cd scripts/qa && QA_BASE=http://localhost:4410 node screenshots.mjs
 *   ../../scripts/qa/make-tour.sh        (stitches the frames into docs/assets/tour.gif)
 *
 * Writes docs/assets/screenshots/NN-name.png and scripts/qa/output/tour/NN.png.
 */
import { mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.QA_BASE ?? "http://localhost:4410";
const EMAIL = process.env.QA_EMAIL ?? "admin@gpuwatch.local";
const PASSWORD = process.env.QA_PASSWORD ?? process.env.GW_DEMO_PASSWORD;
if (!PASSWORD) {
  console.error("Set QA_PASSWORD to the demo password (GW_DEMO_PASSWORD in deploy/compose/.env), or run make screenshots.");
  process.exit(1);
}
const SHOTS = path.resolve(HERE, "../../docs/assets/screenshots");
const TOUR = path.resolve(HERE, "output/tour");
const CHROME = process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH) ? process.env.CHROME_PATH : undefined;
const DESKTOP = { width: 1440, height: 900, deviceScaleFactor: 1 };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let tourIndex = 0;

async function settle(page, ms = 1200) {
  await page.waitForNetworkIdle({ idleTime: 400, timeout: 20_000 }).catch(() => {});
  await sleep(ms);
}

async function shot(page, name, { tour = true, fullPage = false } = {}) {
  await page.evaluate(() => window.scrollTo(0, 0));
  // Park the pointer in an empty corner so no hover tooltip leaks into a capture.
  await page.mouse.move(1, 1);
  await sleep(250);
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage });
  if (tour) await page.screenshot({ path: path.join(TOUR, `${String(++tourIndex).padStart(2, "0")}.png`) });
  console.log(`saved ${name}`);
}

async function clickButton(page, text, { exact = false } = {}) {
  const buttons = await page.$$("button");
  for (const b of buttons) {
    const t = ((await b.evaluate((el) => el.textContent)) ?? "").trim();
    if (exact ? t === text : t.includes(text)) {
      await b.click();
      return;
    }
  }
  throw new Error(`button ${text} not found`);
}

async function visit(page, route, ms = 1500) {
  await page.goto(`${BASE}${route}`, { waitUntil: "networkidle2" });
  await page.waitForSelector("main h1", { timeout: 20_000 });
  await settle(page, ms);
}

/** The id of the GPU the demo runs hot every afternoon (GPU 3 on train-node-01). */
async function hotGpuId(page) {
  return page.evaluate(async () => {
    const gpus = await (await fetch("/api/v1/gpus", { credentials: "include" })).json();
    const g = gpus.find((x) => x.host_name === "train-node-01" && x.index === 3) ?? gpus[0];
    return g.id;
  });
}

async function themedPage(ctx, theme, viewport) {
  const page = await ctx.newPage();
  await page.setViewport(viewport);
  await page.evaluateOnNewDocument((t) => {
    try {
      localStorage.setItem("theme", t);
    } catch {}
  }, theme);
  return page;
}

async function main() {
  await mkdir(SHOTS, { recursive: true });
  await mkdir(TOUR, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
  const ctx = await browser.createBrowserContext();
  const page = await themedPage(ctx, "light", DESKTOP);

  await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
  await sleep(600);
  await shot(page, "00-sign-in", { tour: false });
  await page.type("#email", EMAIL);
  await page.type("#password", PASSWORD);
  await Promise.all([page.waitForNavigation({ waitUntil: "networkidle2" }), page.click("button[type=submit]")]);

  await visit(page, "/", 2000);
  await shot(page, "01-overview");

  // Live tiles fill from the stream; give it a few frames.
  await visit(page, "/live", 3000);
  await shot(page, "02-live");

  const gpu = await hotGpuId(page);
  await visit(page, `/gpus/${gpu}`, 2500);
  await shot(page, "03-gpu-detail");

  await visit(page, "/hosts");
  await shot(page, "04-hosts");

  await visit(page, "/insights");
  await shot(page, "05-insights");

  // The evidence behind the top finding: the numbers the engine used.
  await clickButton(page, "Show evidence");
  await settle(page, 600);
  await shot(page, "06-insight-evidence");

  await visit(page, "/costs", 2000);
  await shot(page, "07-costs");

  // Export a real CSV so the reports list shows one.
  await visit(page, "/costs?tab=reports");
  await page.type("#report-note", "October chargeback");
  await clickButton(page, "Export CSV", { exact: true });
  await settle(page, 1500);
  await shot(page, "08-cost-reports");

  await visit(page, "/alerts");
  await shot(page, "09-alerts");

  await visit(page, "/alerts?tab=rules");
  await shot(page, "10-alert-rules");

  // Open the busiest endpoint so its charts are in the capture.
  const endpoint = await page.evaluate(async () => {
    const eps = await (await fetch("/api/v1/inference/endpoints", { credentials: "include" })).json();
    return eps.find((e) => e.name === "llama-chat")?.id ?? eps[0]?.id ?? "";
  });
  await visit(page, `/inference?endpoint=${endpoint}`, 2500);
  await shot(page, "11-inference");

  await visit(page, "/settings");
  await shot(page, "12-settings", { tour: false });

  const dark = await themedPage(ctx, "dark", DESKTOP);
  await visit(dark, `/gpus/${gpu}`, 2500);
  await shot(dark, "13-dark-mode");

  const phone = await themedPage(ctx, "light", { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await visit(phone, "/", 2000);
  await phone.screenshot({ path: path.join(SHOTS, "14-mobile.png") });
  console.log("saved 14-mobile");

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
