/**
 * Browser QA (make qa): signs in through the real form, visits every dashboard page in
 * light and dark at desktop and phone width, saves screenshots, and fails on console
 * errors, failed or 4xx/5xx requests, broken images, error states and horizontal overflow.
 *
 *   make qa
 *   QA_BASE=http://localhost:4410 QA_OUT=./output node qa.mjs
 *   QA_PAGES=/,/live QA_THEMES=dark QA_SIZES=desktop node qa.mjs
 *
 * Uses Puppeteer's bundled Chromium; set CHROME_PATH to use a local browser instead.
 */
import { mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer";

const BASE = process.env.QA_BASE ?? "http://localhost:4410";
const OUT = process.env.QA_OUT ?? path.resolve("output");
const EMAIL = process.env.QA_EMAIL ?? "admin@gpuwatch.local";
const PASSWORD = process.env.QA_PASSWORD ?? process.env.GW_DEMO_PASSWORD ?? "WatchDemo2026";
const CHROME = process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH) ? process.env.CHROME_PATH : undefined;

const ALL_PAGES = [
  "/login",
  "/",
  "/live",
  "/gpus/:gpu",
  "/hosts",
  "/inference",
  "/insights",
  "/costs",
  "/costs?tab=rates",
  "/costs?tab=rules",
  "/costs?tab=reports",
  "/alerts",
  "/alerts?tab=rules",
  "/alerts?tab=channels",
  "/alerts?tab=deliveries",
  "/keys",
  "/users",
  "/audit",
  "/settings",
];
const PAGES = process.env.QA_PAGES ? process.env.QA_PAGES.split(",") : ALL_PAGES;
const THEMES = (process.env.QA_THEMES ?? "light,dark").split(",");
const SIZES = {
  desktop: { width: 1440, height: 900 },
  phone: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
};
const SIZE_KEYS = (process.env.QA_SIZES ?? "desktop,phone").split(",");
const FULL = process.env.QA_FULL !== "0";

function slug(p) {
  return p === "/" ? "overview" : p.replace(/^\//, "").replace(":gpu", "detail").replace(/[/:?=]/g, "-");
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
  const problems = [];
  let gpuId = null;

  for (const theme of THEMES) {
    for (const sizeKey of SIZE_KEYS) {
      const ctx = await browser.createBrowserContext();
      const page = await ctx.newPage();
      await page.setViewport(SIZES[sizeKey]);
      await page.evaluateOnNewDocument((t) => {
        try {
          localStorage.setItem("theme", t);
        } catch {}
      }, theme);
      const consoleErrors = [];
      page.on("console", (m) => {
        if (m.type() === "error") consoleErrors.push(m.text());
      });
      page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));
      page.on("requestfailed", (r) => {
        const err = r.failure()?.errorText ?? "";
        if (!err.includes("ERR_ABORTED")) consoleErrors.push(`requestfailed ${r.url()} ${err}`);
      });
      page.on("response", (r) => {
        if (r.status() >= 400) consoleErrors.push(`HTTP ${r.status()} ${r.url()}`);
      });

      // Sign in through the real form once per context.
      await page.goto(`${BASE}/login`, { waitUntil: "networkidle2" });
      if (PAGES.includes("/login")) {
        await new Promise((r) => setTimeout(r, 400));
        await page.screenshot({ path: path.join(OUT, `${sizeKey}-${theme}-login.png`) });
      }
      await page.type("#email", EMAIL);
      await page.type("#password", PASSWORD);
      await Promise.all([page.waitForNavigation({ waitUntil: "networkidle2" }), page.click("button[type=submit]")]);

      if (!gpuId) {
        // A GPU with something to explain: the notebook GPU on the demo training node.
        gpuId = await page.evaluate(async () => {
          const gpus = await (await fetch("/api/v1/gpus")).json();
          const pick = gpus.find((g) => g.host_name === "train-node-01" && g.index === 6) ?? gpus[0];
          return pick?.id ?? null;
        });
      }

      for (const p of PAGES) {
        if (p === "/login") continue;
        const url = p.replace(":gpu", String(gpuId ?? "missing"));
        consoleErrors.length = 0;
        await page.goto(`${BASE}${url}`, { waitUntil: "networkidle2", timeout: 45_000 });
        // The page is ready when its heading shows and no skeleton is left.
        await page
          .waitForFunction(() => document.querySelector("main h1") && !document.querySelector("main [data-slot='skeleton']"), { timeout: 30_000 })
          .catch(() => consoleErrors.push("page did not finish loading within 30 s"));
        await new Promise((r) => setTimeout(r, 600));
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        const broken = await page.evaluate(() =>
          [...document.images].filter((img) => img.complete && img.naturalWidth === 0).map((img) => img.src),
        );
        // A healthy page with demo data renders no error states.
        const errorStates = await page.evaluate(() =>
          [...document.querySelectorAll("[data-qa='error-state']")].map((el) => el.textContent?.slice(0, 80) ?? ""),
        );
        const file = path.join(OUT, `${sizeKey}-${theme}-${slug(p)}.png`);
        await page.mouse.move(0, 0);
        await page.screenshot({ path: file, fullPage: FULL });
        const issues = [...consoleErrors];
        if (overflow > 1) issues.push(`horizontal overflow ${overflow}px`);
        for (const src of broken) issues.push(`broken image ${src}`);
        for (const text of errorStates) issues.push(`error state: ${text}`);
        if (issues.length) problems.push({ page: p, theme, size: sizeKey, issues });
        console.log(`${issues.length ? "WARN" : "ok  "} ${sizeKey} ${theme} ${p}${issues.length ? `: ${issues.join(" | ")}` : ""}`);
      }
      await ctx.close();
    }
  }
  await browser.close();
  console.log(`\n${problems.length} page(s) with problems. Screenshots in ${OUT}`);
  if (problems.length) process.exitCode = 1;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
