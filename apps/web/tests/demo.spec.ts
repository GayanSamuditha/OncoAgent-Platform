import { expect, Page, test } from "@playwright/test";

async function login(page: Page, identity: "researcher-console" | "reviewer-console" | "admin-console") {
  await page.goto("/login");
  await page.locator("#user-key").selectOption(identity);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

test.describe("populated synthetic client demonstration", () => {
  test("canonical browser origin preserves the authenticated session", async ({ page }) => {
    const apiHosts = new Set<string>();
    const unauthorizedResponses: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/v1/")) apiHosts.add(new URL(request.url()).host);
    });
    page.on("response", (response) => {
      if (response.url().includes("/api/v1/") && response.status() === 401) {
        unauthorizedResponses.push(response.url());
      }
    });
    await page.goto("/login");
    expect(new URL(page.url()).origin).toBe("http://127.0.0.1:3000");
    await page.locator("#user-key").selectOption("researcher-console");
    const [loginResponse, meResponse] = await Promise.all([
      page.waitForResponse((response) =>
        response.url().endsWith("/backend/api/v1/auth/login"),
      ),
      page.waitForResponse(
        (response) =>
          response.url().endsWith("/backend/api/v1/auth/me") &&
          response.status() === 200,
      ),
      page.getByRole("button", { name: "Sign in" }).click(),
    ]);
    expect(loginResponse.status()).toBe(200);
    expect(meResponse.status()).toBe(200);
    await expect(page).not.toHaveURL(/\/login/);
    expect([...apiHosts]).toEqual(["127.0.0.1:3000"]);
    expect(unauthorizedResponses).toEqual([]);
  });

  test("researcher can open the workspace and demo control center", async ({ page }) => {
    await login(page, "researcher-console");
    await page.goto("/demo");
    await expect(page.getByRole("heading", { name: "Demo Control Center" })).toBeVisible();
    await page.goto("/workflow");
    await expect(page.getByRole("heading", { name: "Research Workspace" })).toBeVisible();
    await expect(page.locator("#request")).toHaveValue(/diabetes and hypertension/);
  });

  test("completed run shows candidates, evidence, and limitations", async ({ page }) => {
    await login(page, "researcher-console");
    await page.goto("/runs");
    await expect(page.getByRole("heading", { name: "My Runs" })).toBeVisible();
    const detail = page.getByRole("link", { name: /Open run details/ }).first();
    await expect(detail).toBeVisible();
    await detail.click();
    await expect(page.getByText("Synthetic result notice.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Supporting evidence" })).toBeVisible();
  });

  test("reviewer can open the inbox without researcher-only navigation", async ({ page }) => {
    await login(page, "reviewer-console");
    await page.goto("/approvals");
    await expect(page.getByRole("heading", { name: "Reviewer Inbox" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Research Workspace" })).toHaveCount(0);
  });

  test("operations pages render their populated or actionable state", async ({ page }) => {
    await login(page, "reviewer-console");
    for (const route of ["/evaluations", "/release-evaluations", "/performance", "/resilience", "/observability", "/security", "/audit"]) {
      await page.goto(route);
      await expect(page.locator("main")).toBeVisible();
      await expect(page.locator("body")).not.toContainText("TypeError");
    }
  });

  test("administrator sees populated catalog, evaluations, and performance", async ({ page }) => {
    await login(page, "admin-console");
    await page.goto("/agent-catalog");
    await expect(page.getByRole("heading", { name: "Unified Agent Catalog" })).toBeVisible();
    await expect(page.locator("article")).not.toHaveCount(0);
    await expect(page.getByText("Agent registry unavailable.")).toHaveCount(0);

    await page.goto("/evaluations");
    await expect(page.getByRole("heading", { name: "Retrieval evaluation" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Cross-framework comparison" })).toBeVisible();
    await expect(page.getByText("Evaluation results are unavailable.")).toHaveCount(0);

    await page.goto("/performance");
    await expect(page.getByRole("heading", { name: "Recent executions" })).toBeVisible();
    await expect(page.locator("tbody tr")).not.toHaveCount(0);
    await expect(page.getByText(/Performance data is unavailable/)).toHaveCount(0);
  });

  test("malformed dataset payload renders a safe empty state", async ({ page }) => {
    await login(page, "researcher-console");
    await page.route("**/api/v1/datasets", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ detail: "malformed" }) }));
    await page.goto("/workflow");
    await expect(page.getByText(/No synthetic datasets are available/)).toBeVisible();
    await expect(page.locator("body")).not.toContainText("TypeError");
  });

  test("backend failure renders recovery guidance", async ({ page }) => {
    await login(page, "researcher-console");
    await page.route("**/api/v1/datasets", (route) => route.abort());
    await page.goto("/workflow");
    await expect(page.getByText("The request could not reach the API.")).toBeVisible();
  });
});
