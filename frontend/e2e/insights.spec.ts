import { expect, test } from "@playwright/test";

import { ADMIN, signIn, watchForClientErrors } from "./helpers";

test.describe("Admin insights", () => {
  test("is reachable from the admin console", async ({ page }) => {
    const problems = watchForClientErrors(page);
    await signIn(page, ADMIN);

    await page.getByRole("link", { name: /Insights/i }).first().click();
    await expect(page).toHaveURL(/\/admin\/insights/);
    await expect(page.getByRole("heading", { name: "Insights" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Data analyst" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Advisor" })).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("the data analyst answers a question and shows the data it read", async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto("/admin/insights");

    await page.getByRole("button", { name: "How much revenue have we made?" }).click();

    // Metric selection and the figures themselves are deterministic SQL, so these hold even
    // when the model is rate-limited and only the narration is missing.
    await expect(page.getByText("Data it read")).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("Revenue", { exact: true }).first()).toBeVisible();
  });

  test("a typed question reaches the analyst", async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto("/admin/insights");

    await page.getByLabel("Question for the data analyst").fill("How many members do we have?");
    await page.getByRole("button", { name: "Ask" }).click();

    await expect(page.getByText("Membership overview")).toBeVisible({ timeout: 90_000 });
  });

  test("an unrelated question is refused honestly", async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto("/admin/insights");

    await page.getByLabel("Question for the data analyst").fill("What is the capital of France?");
    await page.getByRole("button", { name: "Ask" }).click();

    await expect(page.getByText(/do not track anything that answers that/i)).toBeVisible({
      timeout: 90_000,
    });
  });

  test("the advisor tab renders a briefing and prioritised recommendations", async ({ page }) => {
    const problems = watchForClientErrors(page);
    await signIn(page, ADMIN);
    await page.goto("/admin/insights");

    await page.getByRole("button", { name: "Advisor" }).click();

    await expect(page.getByText("Owner's briefing")).toBeVisible({ timeout: 90_000 });
    await expect(page.getByRole("heading", { name: "Recommendations" })).toBeVisible();
    await expect(page.getByText("Evidence").first()).toBeVisible();
    await expect(page.getByText("Do this").first()).toBeVisible();
    await expect(page.getByText(/priority/).first()).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("the advisor report can be refreshed", async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto("/admin/insights");
    await page.getByRole("button", { name: "Advisor" }).click();
    await expect(page.getByText("Owner's briefing")).toBeVisible({ timeout: 90_000 });

    await page.getByRole("button", { name: "Refresh" }).click();
    await expect(page.getByText("Owner's briefing")).toBeVisible({ timeout: 90_000 });
  });

  test("the back link returns to the admin console", async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto("/admin/insights");

    await page.getByRole("link", { name: /Back to admin console/i }).click();
    await expect(page).toHaveURL(/\/admin$/);
  });
});
