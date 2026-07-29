import { expect, Page, test } from "@playwright/test";

async function login(page: Page, identity: "researcher-console" | "reviewer-console") {
  await page.goto("/login");
  await page.locator("#user-key").selectOption(identity);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

test.describe("populated synthetic client demonstration", () => {
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
    await expect(page.getByText(/backend is unavailable/i)).toBeVisible();
  });
});
