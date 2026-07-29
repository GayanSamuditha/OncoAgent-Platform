import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const output = process.env.DEMO_SCREENSHOT_DIR ?? "../../demo_outputs/client-demo-validation/screenshots";
const video = process.env.DEMO_VIDEO_DIR ?? "../../demo_outputs/client-demo-validation/video";
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ recordVideo: { dir: video } });
const page = await context.newPage();
const capture = async (name, path) => { await page.goto(`${baseURL}${path}`); await page.waitForLoadState("networkidle"); await page.screenshot({ path: `${output}/${name}.png`, fullPage: true }); };
const login = async (identity) => { await page.goto(`${baseURL}/login`); await page.locator("#user-key").selectOption(identity); await page.getByRole("button", { name: "Sign in" }).click(); await page.waitForLoadState("networkidle"); };

await login("researcher-console");
await capture("overview", "/");
await capture("demo-control-center", "/demo");
await capture("research-workspace", "/workflow");
await capture("my-runs", "/runs");
const runHref = await page.locator('a[href^="/runs/"]').first().getAttribute("href");
if (runHref) await capture("completed-research-brief", runHref);
await login("reviewer-console");
await capture("reviewer-inbox", "/approvals");
const approvalHref = await page.locator('a[href^="/approvals/"]').first().getAttribute("href");
if (approvalHref) await capture("review-detail", approvalHref);
for (const [name, path] of [["evaluations", "/evaluations"], ["release-gates", "/release-evaluations"], ["performance", "/performance"], ["resilience", "/resilience"], ["observability", "/observability"], ["security", "/security"], ["audit", "/audit"]]) await capture(name, path);
await context.close();
await browser.close();
console.log(`Screenshots written to ${output}`);
