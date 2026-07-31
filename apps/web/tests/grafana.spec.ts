import { expect, test } from "@playwright/test";

const grafana = "http://127.0.0.1:3001";

test.describe("provisioned Grafana operational dashboards", () => {
  test("CrewAI and governance panels render real values and bounded zeros", async ({ page }) => {
    const browserErrors: string[] = [];
    const datasourceFailures: string[] = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    page.on("response", (response) => {
      if (
        response.status() >= 400 &&
        (response.url().includes("/api/ds/query") ||
          response.url().includes("/api/datasources/proxy"))
      ) {
        datasourceFailures.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto(
      `${grafana}/d/oncoagent-crewai/oncoagent-crewai-operations?orgId=1&from=now-15m&to=now&refresh=5s`,
    );
    await expect(page.getByText("Crew outcomes", { exact: true })).toBeVisible();
    await expect(page.getByText("Task duration", { exact: true })).toBeVisible();
    await expect(page.getByText("Process interruptions", { exact: true })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("No data");
    await expect(page.locator("body")).toContainText("accepted");
    await expect(page.locator("body")).toContainText("candidate_discovery");
    await expect(page.locator("body")).toContainText("research_brief_generation");

    await page.goto(
      `${grafana}/d/oncoagent-governance/oncoagent-governance?orgId=1&from=now-15m&to=now&refresh=5s`,
    );
    await expect(page.getByText("Unsafe requests prevented", { exact: true })).toBeVisible();
    await expect(page.getByText("Self-approval denials", { exact: true })).toBeVisible();
    await expect(page.getByText("Orphan MCP requests", { exact: true })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("No data");
    await expect(page.locator("body")).toContainText("self_approval");
    expect(browserErrors).toEqual([]);
    expect(datasourceFailures).toEqual([]);
  });
});
