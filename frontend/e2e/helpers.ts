import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

// The admin is a real account on a shared database, so its credentials stay out of the
// repository. Export E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD before running the admin specs.
export const ADMIN = {
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@example.com",
  password: process.env.E2E_ADMIN_PASSWORD ?? "AdminPass123",
};
export const TRAINER = { email: "trainer@example.com", password: "TrainerPass123" };
export const MEMBER = { email: "member@example.com", password: "MemberPass123" };

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000)}@example.com`;
}

export async function signIn(page: Page, who: { email: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL("http://localhost:5173/");
}

/** Collects console errors and failed requests so silent breakage still fails the test. */
export function watchForClientErrors(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      const text = message.text();
      // React logs a benign warning for autofocus in some setups; keep real errors only.
      if (!text.includes("Download the React DevTools")) problems.push(`console: ${text}`);
    }
  });
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("response", (response) => {
    if (response.status() >= 500) {
      problems.push(`http ${response.status()}: ${response.url()}`);
    }
  });
  return problems;
}

export async function openFitBot(page: Page) {
  await page.getByRole("button", { name: "Chat with FitBot" }).click();
  await expect(page.getByRole("dialog", { name: "FitBot chat" })).toBeVisible();
}

export async function sendToFitBot(page: Page, message: string) {
  await page.getByLabel("Message FitBot").fill(message);
  await page.getByRole("button", { name: "Send" }).click();
}

/** Shown when Gemini is unreachable or the daily free-tier quota is spent. */
export const LLM_UNAVAILABLE = /could not reach the coaching model/i;
