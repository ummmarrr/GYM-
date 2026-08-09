import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

import { ADMIN, MEMBER, TRAINER, signIn, uniqueEmail, watchForClientErrors } from "./helpers";

const FIXTURE_PDF = new URL("./fixtures/protocol.pdf", import.meta.url);

test.describe("Trainer desk", () => {
  test("shows assigned members and the timetable", async ({ page }) => {
    const problems = watchForClientErrors(page);
    await signIn(page, TRAINER);

    await expect(page).toHaveURL(/\/trainer/);
    await expect(page.getByRole("heading", { name: "Trainer desk" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "My members" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Timetable" })).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("a trainer can write a programme for an assigned member", async ({ page }) => {
    await signIn(page, TRAINER);

    const member = page.locator("button", { hasText: "Arjun Patel" }).first();
    await expect(member).toBeVisible();
    await member.click();

    await expect(page.getByRole("heading", { name: /Programme for Arjun/i })).toBeVisible();
    await page.getByLabel("Title").fill("Weeks 1-4 full body");
    await page.getByLabel("Details").fill("Day 1 Squat 3x8\nDay 2 Bench 3x8\nDay 3 Rest");
    await page.getByRole("button", { name: "Assign programme" }).click();

    await expect(page.getByRole("status")).toContainText(/sent to Arjun/i);
    await expect(page.getByRole("heading", { name: "Previously assigned" })).toBeVisible();
  });

  test("a trainer can add a class and then remove it", async ({ page }) => {
    await signIn(page, TRAINER);

    const name = `Test Session ${Date.now()}`;
    await page.getByLabel("Class name").fill(name);
    await page.getByLabel("Discipline").selectOption("yoga");
    await page.getByLabel("Starts at").fill("2030-03-01T07:00");
    await page.getByLabel("Capacity").fill("12");
    await page.getByRole("button", { name: "Add class" }).click();

    await expect(page.getByRole("status")).toContainText(/added to the timetable/i);
    const row = page.locator(".card").filter({ hasText: name }).first();
    await expect(row).toBeVisible();

    await page.getByRole("button", { name: `Remove ${name}` }).click();
    await expect(page.getByRole("status")).toContainText(/removed/i);
  });

  test("a class is listed at the time it was scheduled for, not shifted by a timezone", async ({
    page,
  }) => {
    await signIn(page, TRAINER);

    const name = `Timezone Check ${Date.now()}`;
    await page.getByLabel("Class name").fill(name);
    await page.getByLabel("Starts at").fill("2030-03-01T07:00");
    await page.getByRole("button", { name: "Add class" }).click();
    await expect(page.getByRole("status")).toContainText(/added to the timetable/i);

    const row = page.locator(".card").filter({ hasText: name }).first();
    await expect(row).toContainText("1 Mar");
    await expect(row).toContainText("7:00 am");

    await page.getByRole("button", { name: `Remove ${name}` }).click();
  });

  test("a trainer cannot reach the admin console", async ({ page }) => {
    await signIn(page, TRAINER);

    await page.goto("/admin");
    await expect(page).toHaveURL(/\/trainer/);

    await page.goto("/admin/insights");
    await expect(page).toHaveURL(/\/trainer/);
  });
});

test.describe("Admin console", () => {
  test("shows the stat cards, accounts table and knowledge base", async ({ page }) => {
    const problems = watchForClientErrors(page);
    await signIn(page, ADMIN);

    await expect(page).toHaveURL(/\/admin/);
    await expect(page.getByRole("heading", { name: "Admin console" })).toBeVisible();
    await expect(page.getByText("Members", { exact: true })).toBeVisible();
    await expect(page.getByText("Revenue", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "All accounts" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "FitBot knowledge base" })).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("an admin can create a member account", async ({ page }) => {
    await signIn(page, ADMIN);

    const email = uniqueEmail("created");
    await page.getByLabel("Full name").fill("Created Member");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Temporary password").fill("TempPass1234");
    await page.getByLabel("Role").selectOption("member");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByRole("status")).toContainText(/added as member/i);
    await expect(page.getByText(email)).toBeVisible();
  });

  test("an admin can promote an account to trainer and back", async ({ page }) => {
    await signIn(page, ADMIN);

    const email = uniqueEmail("promote");
    await page.getByLabel("Full name").fill("Promote Me");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Temporary password").fill("TempPass1234");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByText(email)).toBeVisible();

    const row = page.locator("tr", { hasText: email });
    await row.locator("select").first().selectOption("trainer");
    await expect(page.getByRole("status")).toContainText(/is now a trainer/i);
  });

  test("an admin can deactivate and reactivate an account", async ({ page }) => {
    await signIn(page, ADMIN);

    const email = uniqueEmail("toggle");
    await page.getByLabel("Full name").fill("Toggle Me");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Temporary password").fill("TempPass1234");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByText(email)).toBeVisible();

    const row = page.locator("tr", { hasText: email });
    await row.getByText("active").click();
    await expect(page.getByRole("status")).toContainText(/deactivated/i);
    await expect(row.getByText("inactive")).toBeVisible();

    await row.getByText("inactive").click();
    await expect(page.getByRole("status")).toContainText(/reactivated/i);
  });

  test("an admin can assign a trainer to a member", async ({ page }) => {
    await signIn(page, ADMIN);

    const row = page.locator("tr", { hasText: "member@example.com" });
    const trainerSelect = row.locator("select").nth(1);
    await trainerSelect.selectOption({ label: "Riya Sharma" });

    await expect(page.getByRole("status")).toContainText(/Trainer assigned/i);
  });

  test("an admin can ingest a PDF into the knowledge base and remove it again", async ({ page }) => {
    await signIn(page, ADMIN);

    await page.getByLabel("PDF file").setInputFiles(fileURLToPath(FIXTURE_PDF));
    await page.getByLabel("Discipline").selectOption("gym");
    await page.getByRole("button", { name: "Ingest PDF" }).click();

    await expect(page.getByRole("status")).toContainText(/protocol\.pdf ingested into gym/i, {
      timeout: 60_000,
    });

    const card = page.locator(".card").filter({ hasText: "protocol.pdf" }).first();
    await expect(card).toContainText("chunks");

    await page.getByRole("button", { name: "Remove protocol.pdf" }).click();
    await expect(page.getByRole("status")).toContainText(/removed/i);
  });

  test("an admin cannot demote their own account", async ({ page }) => {
    await signIn(page, ADMIN);

    const row = page.locator("tr", { hasText: ADMIN.email });
    await row.locator("select").first().selectOption("member");

    await expect(page.getByRole("alert")).toContainText(/cannot change your own role/i);
  });
});

test.describe("Cross-role flow", () => {
  test("a programme written by a trainer shows up on the member's dashboard", async ({ page }) => {
    const title = `Handoff plan ${Date.now()}`;

    await signIn(page, TRAINER);
    await page.locator("button", { hasText: "Arjun Patel" }).first().click();
    await page.getByLabel("Type").selectOption("diet");
    await page.getByLabel("Title").fill(title);
    await page.getByLabel("Details").fill("Breakfast: oats and eggs. Lunch: rice, dal, salad.");
    await page.getByRole("button", { name: "Assign programme" }).click();
    await expect(page.getByRole("status")).toContainText(/sent to Arjun/i);

    await page.getByRole("button", { name: "Sign out" }).click();

    await signIn(page, MEMBER);
    const card = page.locator(".card").filter({ hasText: title }).first();
    await expect(card).toBeVisible();
    await expect(card).toContainText("Breakfast: oats and eggs");
    await expect(card).toContainText("diet");
  });
});
