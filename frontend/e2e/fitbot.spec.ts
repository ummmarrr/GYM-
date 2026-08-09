import { expect, test } from "@playwright/test";

import {
  MEMBER,
  openFitBot,
  sendToFitBot,
  signIn,
  uniqueEmail,
  watchForClientErrors,
} from "./helpers";

test.describe("FitBot widget", () => {
  test("opens for a signed-out visitor and shows starter prompts", async ({ page }) => {
    const problems = watchForClientErrors(page);
    await page.goto("/");
    await openFitBot(page);

    await expect(page.getByText(/I'm FitBot/i)).toBeVisible();
    await expect(page.getByText("Reception · Gym · Yoga · MMA")).toBeVisible();
    await expect(page.getByRole("button", { name: "What packages do you have?" })).toBeVisible();

    expect(problems).toEqual([]);
  });

  test("closes with the close button and with Escape", async ({ page }) => {
    await page.goto("/");
    await openFitBot(page);
    await page.getByRole("button", { name: "Close chat" }).click();
    await expect(page.getByRole("dialog", { name: "FitBot chat" })).toBeHidden();

    await openFitBot(page);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "FitBot chat" })).toBeHidden();
  });

  test("answers a training question for a signed-out visitor", async ({ page }) => {
    const problems = watchForClientErrors(page);
    await page.goto("/");
    await openFitBot(page);
    await sendToFitBot(page, "Give me a beginner push day workout");

    // The reply is either real coaching or, if the Gemini quota is spent, a plain-language
    // apology. Either is acceptable; a blank bubble or a 500 is not.
    const reply = page.locator("[data-testid='fitbot-message']").last();
    await expect(reply).toContainText(/\w+(\s+\w+){8,}/s, { timeout: 90_000 });
    await expect(reply).not.toContainText(/Something went wrong/i);

    expect(problems).toEqual([]);
  });

  test("a visitor asking about their plan gets the secure sign-in card, not a password prompt", async ({
    page,
  }) => {
    await page.goto("/");
    await openFitBot(page);
    await sendToFitBot(page, "when does my plan expire?");

    await expect(page.getByText("Secure sign in")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByPlaceholder("Email")).toBeVisible();
    await expect(page.getByText(/never part of the chat/i)).toBeVisible();
  });

  test("a visitor can sign in from inside the chat and continue", async ({ page }) => {
    await page.goto("/");
    await openFitBot(page);
    await sendToFitBot(page, "when does my plan expire?");
    await expect(page.getByText("Secure sign in")).toBeVisible({ timeout: 60_000 });

    await page.getByPlaceholder("Email").fill(MEMBER.email);
    await page.getByPlaceholder("Password", { exact: true }).fill(MEMBER.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText(/You're signed in/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Coaching Arjun/i)).toBeVisible();
  });

  test("a visitor asking to join gets the secure signup card and can register", async ({ page }) => {
    await page.goto("/");
    await openFitBot(page);
    await sendToFitBot(page, "I want to sign up");

    await expect(page.getByText("Secure sign up")).toBeVisible({ timeout: 60_000 });

    await page.getByPlaceholder("Full name").fill("Chat Joiner");
    await page.getByPlaceholder("Email").fill(uniqueEmail("chatjoiner"));
    await page.getByPlaceholder(/Password \(min 8/).fill("StrongPass123");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByText(/You're signed in/i)).toBeVisible({ timeout: 30_000 });
  });

  test("a risky health question is escalated to a human", async ({ page }) => {
    await page.goto("/");
    await openFitBot(page);
    await sendToFitBot(page, "I get chest pain when I run");

    await expect(page.getByText("Flagged for a human trainer")).toBeVisible({ timeout: 60_000 });
  });

  test("a signed-in member sees their name in the widget header", async ({ page }) => {
    await signIn(page, MEMBER);
    await openFitBot(page);

    await expect(page.getByText(/Coaching Arjun/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Open my dashboard" })).toBeVisible();
  });
});
