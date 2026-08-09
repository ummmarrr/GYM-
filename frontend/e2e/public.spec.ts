import { expect, test } from "@playwright/test";

import { uniqueEmail, watchForClientErrors } from "./helpers";

test.describe("Public site", () => {
  test("landing page renders its hero, sections and footer", async ({ page }) => {
    const problems = watchForClientErrors(page);
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Train with intent/i })).toBeVisible();
    await expect(page.getByText("Strength & Conditioning")).toBeVisible();
    await expect(page.getByText("Yoga & Mobility")).toBeVisible();
    await expect(page.getByText("MMA & Striking")).toBeVisible();
    await expect(page.getByRole("heading", { name: /A gym that answers back/i })).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("header navigation reaches packages and auth pages", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("link", { name: "Packages", exact: true }).click();
    await expect(page).toHaveURL(/\/packages/);

    await page.getByRole("link", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/login/);

    await page.getByRole("link", { name: "Create an account" }).click();
    await expect(page).toHaveURL(/\/join/);
  });

  test("packages page lists all three packages with prices", async ({ page }) => {
    const problems = watchForClientErrors(page);
    await page.goto("/packages");

    await expect(page.getByRole("heading", { name: "Starter" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Performance" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Complete" })).toBeVisible();
    await expect(page.getByText("Most popular")).toBeVisible();
    await expect(page.getByText("₹1,499")).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("a signed-out visitor choosing a package is sent to signup", async ({ page }) => {
    await page.goto("/packages");
    await page.getByRole("button", { name: "Join and choose" }).first().click();

    await expect(page).toHaveURL(/\/join/);
  });

  test("unknown routes show the 404 page", async ({ page }) => {
    await page.goto("/this-route-does-not-exist");

    await expect(page.getByText("404")).toBeVisible();
    await expect(page.getByRole("heading", { name: /skipped leg day/i })).toBeVisible();

    await page.getByRole("link", { name: "Back to home" }).click();
    await expect(page).toHaveURL("http://localhost:5173/");
  });

  test("protected routes bounce a signed-out visitor to login", async ({ page }) => {
    for (const route of ["/dashboard", "/trainer", "/admin", "/admin/insights"]) {
      await page.goto(route);
      await expect(page).toHaveURL(/\/login/);
    }
  });

  test("mobile menu opens and navigates", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    await page.getByRole("button", { name: "Open menu" }).click();
    await page.getByRole("link", { name: "Packages", exact: true }).click();

    await expect(page).toHaveURL(/\/packages/);
  });
});

test.describe("Registration and login", () => {
  test("a new visitor can sign up and lands on the member dashboard", async ({ page }) => {
    const problems = watchForClientErrors(page);
    const email = uniqueEmail("newjoiner");

    await page.goto("/join");
    await page.getByLabel("Full name").fill("New Joiner");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Phone").fill("9876543210");
    await page.getByLabel("Password").fill("StrongPass123");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole("heading", { name: /Hi New/i })).toBeVisible();
    await expect(page.getByText("No active package")).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("signing up with an existing email shows a clear error", async ({ page }) => {
    await page.goto("/join");
    await page.getByLabel("Full name").fill("Duplicate Person");
    await page.getByLabel("Email").fill("member@example.com");
    await page.getByLabel("Password").fill("StrongPass123");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByRole("alert")).toContainText(/already exists/i);
  });

  test("a wrong password shows an error and does not sign the user in", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("member@example.com");
    await page.getByLabel("Password").fill("DefinitelyWrong123");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("alert")).toContainText(/Incorrect email or password/i);
    await expect(page).toHaveURL(/\/login/);
  });
});
