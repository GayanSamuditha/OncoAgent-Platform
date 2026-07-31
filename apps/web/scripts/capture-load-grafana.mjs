import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const repository = path.resolve(process.cwd(), "../..");
const outputsRoot = path.join(repository, "loadtest_outputs");
const requestedOutput = process.env.LOAD_TEST_OUTPUT;
const candidates = fs.existsSync(outputsRoot)
  ? fs
      .readdirSync(outputsRoot)
      .filter((name) => name.startsWith("loadtest-"))
      .map((name) => path.join(outputsRoot, name))
      .filter((item) => fs.existsSync(path.join(item, "summary.json")))
      .sort(
        (left, right) =>
          fs.statSync(path.join(right, "summary.json")).mtimeMs -
          fs.statSync(path.join(left, "summary.json")).mtimeMs,
      )
  : [];
const output = requestedOutput ? path.resolve(requestedOutput) : candidates[0];
if (!output) {
  throw new Error("No completed local load-test output is available.");
}

const summary = JSON.parse(
  fs.readFileSync(path.join(output, "summary.json"), "utf8"),
);
const from = Date.parse(summary.start_time);
const to = Date.parse(summary.end_time);
if (!Number.isFinite(from) || !Number.isFinite(to)) {
  throw new Error("The load-test report does not contain a valid execution window.");
}

const dashboardDirectory = path.join(
  repository,
  "infra/observability/grafana/dashboards",
);
const dashboards = fs
  .readdirSync(dashboardDirectory)
  .filter((name) => name.endsWith(".json"))
  .map((name) =>
    JSON.parse(fs.readFileSync(path.join(dashboardDirectory, name), "utf8")),
  )
  .filter((dashboard) => dashboard.uid && dashboard.title);

const screenshotDirectory = path.join(output, "screenshots");
const grafanaDirectory = path.join(output, "grafana");
const tracePath = path.join(grafanaDirectory, "playwright-trace.zip");
fs.mkdirSync(screenshotDirectory, { recursive: true });
fs.mkdirSync(grafanaDirectory, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1100 },
});
await context.tracing.start({
  screenshots: true,
  snapshots: true,
  sources: false,
});
const page = await context.newPage();
const javascriptErrors = [];
const datasourceFailures = [];
page.on("pageerror", (error) => javascriptErrors.push(error.message));
page.on("response", (response) => {
  if (
    response.status() >= 400 &&
    (response.url().includes("/api/ds/query") ||
      response.url().includes("/api/datasources/proxy"))
  ) {
    datasourceFailures.push({
      status: response.status(),
      path: new URL(response.url()).pathname,
    });
  }
});

const results = [];
try {
  for (const dashboard of dashboards) {
    const slug = String(dashboard.title)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    const url =
      `http://127.0.0.1:3001/d/${encodeURIComponent(dashboard.uid)}/${slug}` +
      `?orgId=1&from=${from}&to=${to}&refresh=5s`;
    await page.goto(url, { waitUntil: "networkidle", timeout: 60_000 });
    await page.getByText(dashboard.title, { exact: true }).first().waitFor({
      state: "visible",
      timeout: 20_000,
    });
    await page.waitForTimeout(6_000);
    const body = await page.locator("body").innerText();
    const noData = (body.match(/\bNo data\b/g) ?? []).length;
    const screenshot = path.join(screenshotDirectory, `${slug}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    results.push({
      dashboard: dashboard.title,
      uid: dashboard.uid,
      no_data_panels: noData,
      screenshot,
    });
  }
} finally {
  await context.tracing.stop({ path: tracePath });
  await browser.close();
}

const report = {
  generated_at: new Date().toISOString(),
  execution_window: { from: summary.start_time, to: summary.end_time },
  dashboards: results,
  playwright_trace: tracePath,
  javascript_errors: javascriptErrors,
  datasource_failures: datasourceFailures,
};
fs.writeFileSync(
  path.join(grafanaDirectory, "playwright-validation.json"),
  `${JSON.stringify(report, null, 2)}\n`,
);
summary.artifacts = {
  ...(summary.artifacts ?? {}),
  screenshots: results.map((item) => item.screenshot),
  grafana_validation: path.join(
    grafanaDirectory,
    "playwright-validation.json",
  ),
  playwright_trace: tracePath,
};
fs.writeFileSync(
  path.join(output, "summary.json"),
  `${JSON.stringify(summary, null, 2)}\n`,
);

const unexpectedNoData = results.filter((item) => item.no_data_panels > 0);
if (
  unexpectedNoData.length > 0 ||
  javascriptErrors.length > 0 ||
  datasourceFailures.length > 0
) {
  throw new Error("Grafana load-test validation found unavailable panels or browser errors.");
}
console.log(
  JSON.stringify({
    status: "passed",
    dashboards: results.length,
    screenshot_directory: screenshotDirectory,
    playwright_trace: tracePath,
  }),
);
