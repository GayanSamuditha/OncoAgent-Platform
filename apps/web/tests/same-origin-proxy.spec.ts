import { expect, Page, test } from "@playwright/test";

const datasetId = "6b15ce38-e12c-4482-866e-59d333952024";
const runPayload = {
  dataset_id: datasetId,
  request: "Identify synthetic patients with diabetes and hypertension for research review.",
  criteria: [
    {
      criterion_id: "criterion-1",
      criterion_type: "condition",
      clinical_concept: "diabetes",
      operator: "contains",
      required: true,
    },
    {
      criterion_id: "criterion-2",
      criterion_type: "condition",
      clinical_concept: "hypertension",
      operator: "contains",
      required: true,
    },
  ],
  max_candidates: 20,
  planner_provider: "deterministic",
};

async function login(
  page: Page,
  identity:
    | "researcher-console"
    | "reviewer-console"
    | "operator-console",
) {
  await page.goto("/login");
  await page.locator("#user-key").selectOption(identity);
  const [loginResponse, meResponse] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().endsWith("/backend/api/v1/auth/login") &&
        response.request().method() === "POST",
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
  return loginResponse;
}

async function browserPost(
  page: Page,
  path: string,
  payload: Record<string, unknown>,
): Promise<{ status: number; body: Record<string, unknown> }> {
  return page.evaluate(
    async ({ requestPath, requestPayload }) => {
      const response = await fetch(requestPath, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(requestPayload),
      });
      return {
        status: response.status,
        body: (await response.json()) as Record<string, unknown>,
      };
    },
    { requestPath: path, requestPayload: payload },
  );
}

test.describe.serial("same-origin backend proxy", () => {
  test("forwards login cookies, auth/me, and logout on the browser origin", async ({
    page,
    context,
  }) => {
    const directApiRequests: string[] = [];
    const forbiddenHeaders: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.port === "8000") directApiRequests.push(request.url());
      if (
        request.headers()["x-actor-id"] ||
        request.headers()["x-actor-role"] ||
        request.headers().authorization === ""
      ) {
        forbiddenHeaders.push(request.url());
      }
    });

    const loginResponse = await login(page, "researcher-console");
    const responseHeaders = await loginResponse.allHeaders();
    expect(responseHeaders["set-cookie"]).toContain("HttpOnly");
    expect(responseHeaders["set-cookie"]).toContain("SameSite=lax");

    const cookies = await context.cookies("http://127.0.0.1:3000");
    const sessionCookie = cookies.find((cookie) => cookie.httpOnly);
    expect(sessionCookie).toBeDefined();
    expect(sessionCookie?.secure).toBe(false);

    const me = await page.evaluate(async () => {
      const response = await fetch("/backend/api/v1/auth/me", {
        credentials: "include",
      });
      return { status: response.status, body: await response.json() };
    });
    expect(me.status).toBe(200);
    expect(me.body).toMatchObject({ role: "researcher" });

    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login/);
    const afterLogout = await page.evaluate(async () =>
      (await fetch("/backend/api/v1/auth/me", { credentials: "include" })).status,
    );
    expect(afterLogout).toBe(401);
    expect(directApiRequests).toEqual([]);
    expect(forbiddenHeaders).toEqual([]);
  });

  test("keeps researcher and reviewer sessions isolated", async ({ browser }) => {
    const researcherContext = await browser.newContext({
      baseURL: "http://127.0.0.1:3000",
    });
    const reviewerContext = await browser.newContext({
      baseURL: "http://127.0.0.1:3000",
    });
    try {
      const researcherPage = await researcherContext.newPage();
      const reviewerPage = await reviewerContext.newPage();
      await login(researcherPage, "researcher-console");
      await login(reviewerPage, "reviewer-console");
      const [researcher, reviewer] = await Promise.all([
        researcherPage.evaluate(async () =>
          (
            await fetch("/backend/api/v1/auth/me", {
              credentials: "include",
            })
          ).json(),
        ),
        reviewerPage.evaluate(async () =>
          (
            await fetch("/backend/api/v1/auth/me", {
              credentials: "include",
            })
          ).json(),
        ),
      ]);
      expect(researcher).toMatchObject({ role: "researcher" });
      expect(reviewer).toMatchObject({ role: "reviewer" });
    } finally {
      await researcherContext.close();
      await reviewerContext.close();
    }
  });

  test("retrieves the bounded dataset and creates a real run without CORS", async ({
    page,
  }) => {
    const optionsRequests: string[] = [];
    const directApiRequests: string[] = [];
    const failedRequiredRequests: string[] = [];
    const consoleErrors: string[] = [];
    const forbiddenHeaders: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (request.method() === "OPTIONS") optionsRequests.push(request.url());
      if (url.port === "8000") directApiRequests.push(request.url());
      if (
        request.headers()["x-actor-id"] ||
        request.headers()["x-actor-role"] ||
        request.headers().authorization === ""
      ) {
        forbiddenHeaders.push(request.url());
      }
    });
    page.on("response", (response) => {
      if (
        response.url().includes("/backend/api/v1/") &&
        response.status() >= 400
      ) {
        failedRequiredRequests.push(`${response.status()} ${response.url()}`);
      }
    });
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });

    await login(page, "researcher-console");
    const datasetResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/backend/api/v1/datasets") &&
        response.status() === 200,
    );
    await page.goto("/workflow");
    const datasetResponse = await datasetResponsePromise;
    expect(datasetResponse.status()).toBe(200);
    await expect(page.locator("#dataset")).toContainText(
      "synthea-eval-100 · 100 synthetic patients",
    );
    await expect(page.locator("#dataset")).toHaveValue(datasetId);
    await page.getByLabel("Planner provider").selectOption("deterministic");

    const createResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/backend/api/v1/runs") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Start governed research run" })
      .click();
    const createResponse = await createResponsePromise;
    expect(createResponse.status()).toBe(201);
    const run = (await createResponse.json()) as {
      run_id: string;
      approval_id?: string;
      status: string;
    };
    expect(run.run_id).toBeTruthy();
    expect(run.approval_id).toBeTruthy();
    await expect(page).toHaveURL(new RegExp(`/runs/${run.run_id}$`));
    await expect(page.getByText("Research brief", { exact: true })).toBeVisible();
    await expect(page.getByText(/backend is unavailable/i)).toHaveCount(0);
    await expect(page.getByText(/request could not reach the API/i)).toHaveCount(0);

    const selfApproval = await browserPost(
      page,
      `/backend/api/v1/approvals/${run.approval_id}/decision`,
      { decision: "approve", comment: "Self-approval denial regression check." },
    );
    expect(selfApproval.status).toBe(403);

    await page.getByRole("button", { name: "Log out" }).click();
    await login(page, "reviewer-console");
    const reviewerApproval = await browserPost(
      page,
      `/backend/api/v1/approvals/${run.approval_id}/decision`,
      { decision: "approve", comment: "Approved for synthetic research." },
    );
    expect(reviewerApproval.status).toBe(200);
    expect(reviewerApproval.body).toMatchObject({
      run_id: run.run_id,
      status: "completed",
    });

    expect(optionsRequests).toEqual([]);
    expect(directApiRequests).toEqual([]);
    expect(forbiddenHeaders).toEqual([]);
    expect(consoleErrors.filter((entry) => /cors/i.test(entry))).toEqual([]);
    expect(
      failedRequiredRequests.filter(
        (entry) =>
          !entry.startsWith("403 ") ||
          !entry.includes(`/approvals/${run.approval_id}/decision`),
      ),
    ).toEqual([]);
  });

  test("preserves workflow-create authorization through the proxy", async ({
    page,
  }) => {
    await page.goto("/login");
    const unauthenticated = await browserPost(
      page,
      "/backend/api/v1/runs",
      runPayload,
    );
    expect(unauthenticated.status).toBe(401);

    await login(page, "operator-console");
    const operator = await browserPost(
      page,
      "/backend/api/v1/runs",
      runPayload,
    );
    expect(operator.status).toBe(403);
  });

  for (const errorCase of [
    {
      status: 401,
      body: { detail: "not authenticated" },
      message: "Your session has expired. Sign in again.",
    },
    {
      status: 403,
      body: { detail: "internal policy detail" },
      message: "You do not have permission to perform this action.",
    },
    {
      status: 422,
      body: { detail: [{ msg: "Dataset is required." }] },
      message: "Dataset is required.",
    },
    {
      status: 500,
      body: { detail: "database internals" },
      message: "The backend encountered an error.",
    },
  ]) {
    test(`maps HTTP ${errorCase.status} accurately`, async ({ page }) => {
      await login(page, "researcher-console");
      await page.route("**/backend/api/v1/datasets", (route) =>
        route.fulfill({
          status: errorCase.status,
          contentType: "application/json",
          body: JSON.stringify(errorCase.body),
        }),
      );
      await page.goto("/workflow");
      await expect(page.getByText(errorCase.message, { exact: true })).toBeVisible();
    });
  }

  test("maps a browser network failure accurately", async ({ page }) => {
    await login(page, "researcher-console");
    await page.route("**/backend/api/v1/datasets", (route) => route.abort());
    await page.goto("/workflow");
    await expect(
      page.getByText("The request could not reach the API.", { exact: true }),
    ).toBeVisible();
  });
});
