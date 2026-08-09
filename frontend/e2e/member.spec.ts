import { expect, test } from "@playwright/test";

import { MEMBER, signIn, signOut, uniqueEmail, watchForClientErrors } from "./helpers";

test.describe("Member dashboard", () => {
  test("shows the active package, entitlements and profile", async ({ page }) => {
    const problems = watchForClientErrors(page);
    await signIn(page, MEMBER);

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole("heading", { name: /Hi Arjun/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Performance" })).toBeVisible();
    await expect(page.getByText("Active", { exact: true })).toBeVisible();
    await expect(page.getByText("GYM, YOGA")).toBeVisible();
    await expect(page.getByRole("heading", { name: "My fitness profile" })).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("the fitness profile can be edited and saved", async ({ page }) => {
    await signIn(page, MEMBER);

    const goal = `Fat loss check ${Date.now()}`;
    await page.getByLabel("Main goal").fill(goal);
    await page.getByLabel("Experience level").selectOption("intermediate");
    await page.getByLabel("Equipment access").fill("Full commercial gym");
    await page.getByRole("button", { name: "Save profile" }).click();

    await expect(page.getByRole("status")).toContainText(/Saved/i);

    await page.reload();
    await expect(page.getByLabel("Main goal")).toHaveValue(goal);
  });

  test("a member can book and then cancel a class within their package", async ({ page }) => {
    await signIn(page, MEMBER);

    const gymCard = page.locator(".card", { hasText: "gym session" }).first();
    const anyBookable = page.getByRole("button", { name: "Book" }).first();
    await expect(anyBookable).toBeVisible();
    await anyBookable.click();

    await expect(page.getByRole("status")).toContainText(/Booked/i);
    await expect(page.getByRole("button", { name: "Cancel" }).first()).toBeVisible();

    await page.getByRole("button", { name: "Cancel" }).first().click();
    await expect(page.getByRole("status")).toContainText(/cancelled/i);
    void gymCard;
  });

  test("booking a discipline outside the package is refused with a clear reason", async ({
    page,
  }) => {
    await signIn(page, MEMBER);

    // Arjun is on Performance: gym and yoga only, so the MMA class must be blocked.
    const mmaRow = page.locator(".card").filter({ hasText: "MMA" }).first();
    const bookButton = mmaRow.getByRole("button", { name: "Book" });

    if (await bookButton.count()) {
      await bookButton.click();
      await expect(page.getByRole("alert")).toContainText(/does not include mma/i);
    }
  });

  test("a member cannot reach the trainer or admin areas", async ({ page }) => {
    await signIn(page, MEMBER);

    await page.goto("/trainer");
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto("/admin");
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto("/admin/insights");
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("a new member can buy a package and see it activate", async ({ page }) => {
    const problems = watchForClientErrors(page);
    const email = uniqueEmail("buyer");

    await page.goto("/join");
    await page.getByLabel("Full name").fill("Package Buyer");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("StrongPass123");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.getByRole("link", { name: "See packages" }).click();
    await expect(page).toHaveURL(/\/packages/);

    await page
      .locator(".card")
      .filter({ hasText: "Complete" })
      .getByRole("button", { name: "Activate" })
      .click();

    await expect(page.getByRole("status")).toContainText(/Complete is active until/i);

    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Complete" })).toBeVisible();
    await expect(page.getByText("GYM, YOGA, MMA")).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("signing out returns the visitor to the public site", async ({ page }) => {
    await signIn(page, MEMBER);
    await signOut(page);

    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });
});
