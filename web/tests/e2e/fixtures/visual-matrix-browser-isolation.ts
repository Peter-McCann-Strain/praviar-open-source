import type { Page } from "@playwright/test";
import {
  DEMO_ONBOARDING_IDENTITY,
  DEV_ONBOARDING_IDENTITY,
  type OnboardingStorageIdentity,
} from "../../../src/lib/onboarding-storage";

type OnboardingStorageKeys = {
  tour: string;
  welcome: string;
};

export const VISUAL_MATRIX_FIXED_TIME = "2026-07-17T12:00:00.000Z";

export function visualMatrixOnboardingIdentityForProfile(
  profile: "api" | "demo",
): OnboardingStorageIdentity {
  return profile === "demo"
    ? DEMO_ONBOARDING_IDENTITY
    : DEV_ONBOARDING_IDENTITY;
}

function hasMutableOrigin(url: string): boolean {
  try {
    const protocol = new URL(url).protocol;
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * Disables browser HTTP-cache reuse for the capture surface. Install this
 * catch-all before state fixtures: Playwright evaluates the most recently
 * registered matching route first, so the fixture routes retain priority.
 */
export async function installVisualMatrixHttpCacheBypass(
  page: Page,
): Promise<void> {
  await page.route("**/*", async (route) => {
    const headers = Object.fromEntries(
      Object.entries(route.request().headers()).filter(
        ([name]) => !["cache-control", "pragma"].includes(name.toLowerCase()),
      ),
    );
    await route.continue({
      headers: {
        ...headers,
        "cache-control": "no-cache, no-store, max-age=0",
        pragma: "no-cache",
      },
    });
  });
}

export async function installVisualMatrixFixedTime(page: Page): Promise<void> {
  await page.clock.setFixedTime(VISUAL_MATRIX_FIXED_TIME);
}

/**
 * Restores the browser-owned state that survives a full page navigation. App
 * module state is naturally replaced by page.goto; context state is not.
 */
export async function resetVisualMatrixBrowserState(
  page: Page,
  {
    firstRun,
    onboardingKeys,
  }: {
    firstRun: boolean;
    onboardingKeys: OnboardingStorageKeys;
  },
): Promise<void> {
  await page.context().clearCookies();
  await page.context().clearPermissions();

  if (!hasMutableOrigin(page.url())) return;

  await page.evaluate(
    async ({ firstRun: shouldShowFirstRun, onboardingKeys: keys }) => {
      window.localStorage.clear();
      window.sessionStorage.clear();
      if (!shouldShowFirstRun) {
        window.localStorage.setItem(keys.welcome, "true");
        window.localStorage.setItem(keys.tour, "true");
      }

      if ("serviceWorker" in navigator) {
        const registrations = await navigator.serviceWorker.getRegistrations();
        await Promise.all(
          registrations.map((registration) => registration.unregister()),
        );
      }
      if ("caches" in window) {
        const cacheNames = await window.caches.keys();
        await Promise.all(cacheNames.map((name) => window.caches.delete(name)));
      }
    },
    { firstRun, onboardingKeys },
  );
}

/**
 * Installs capture-only randomness in the current document realm. Unlike an
 * init script, this cannot leak into the next surface navigation.
 */
export async function installVisualMatrixSurfaceRandomness(
  page: Page,
  surfaceName: string,
): Promise<void> {
  if (surfaceName !== "settings-api-key-reveal") return;
  await page.evaluate(() => {
    Math.random = () => 0.3141592653589793;
  });
}
