import { expect, type Page } from "@playwright/test";

const SETTLED_STYLE = `
  *, *::before, *::after {
    animation-delay: 0s !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-delay: 0s !important;
    transition-duration: 0.01ms !important;
  }
`;

export async function waitForDeterministicSurface(
  page: Page,
  label: string,
  {
    allowAppError = false,
    allowExpectedFrameworkErrorIndicator = false,
  }: {
    allowAppError?: boolean;
    allowExpectedFrameworkErrorIndicator?: boolean;
  } = {},
): Promise<void> {
  await expect(page.locator("h1").first(), `${label} primary h1`).toBeVisible({
    timeout: 20_000,
  });
  await expect
    .poll(async () => (await page.title()).trim(), {
      message: `${label} non-empty document title`,
      timeout: 20_000,
    })
    .not.toBe("");
  await expect(
    page.locator('[data-praviar-app-state="loading"]'),
    `${label} loading state`,
  ).toHaveCount(0, { timeout: 20_000 });
  if (!allowAppError) {
    await expect(
      page.locator('[data-praviar-app-state="error"]'),
      `${label} application error state`,
    ).toHaveCount(0);
  }
  if (allowExpectedFrameworkErrorIndicator) {
    await page.evaluate(() => {
      for (const portal of document.querySelectorAll<HTMLElement>(
        "nextjs-portal",
      )) {
        if (
          portal.shadowRoot
            ?.querySelector("[data-next-badge]")
            ?.getAttribute("data-error") === "true"
        ) {
          portal.style.setProperty("display", "none", "important");
        }
      }
    });
  } else {
    await expect
      .poll(
        () =>
          page.evaluate(() =>
            Array.from(document.querySelectorAll("nextjs-portal")).some(
              (portal) =>
                portal.shadowRoot
                  ?.querySelector("[data-next-badge]")
                  ?.getAttribute("data-error") === "true",
            ),
          ),
        { message: `${label} Next.js error overlay`, timeout: 5_000 },
      )
      .toBe(false);
  }

  await page.addStyleTag({ content: SETTLED_STYLE });
  await page.evaluate(async () => {
    await document.fonts?.ready;
    for (const image of Array.from(document.images)) image.loading = "eager";
  });
  await expect
    .poll(
      () =>
        page.evaluate(() =>
          Array.from(document.images)
            .filter((image) => !image.complete || image.naturalWidth === 0)
            .map((image) => image.currentSrc || image.src || "[missing src]"),
        ),
      {
        message: `${label} incomplete or undecodable images`,
        timeout: 20_000,
      },
    )
    .toEqual([]);
  await page.evaluate(async () => {
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
  });

  await expect(
    page.locator(
      '[data-praviar-counter-state]:not([data-praviar-counter-state="settled"])',
    ),
    `${label} unsettled numeric counters`,
  ).toHaveCount(0, { timeout: 10_000 });

  // Drive finite entrance/transition animations to their intended settled
  // frame before capture. Infinite or indeterminate animations are deliberately
  // left running so the hard gate below still vetoes non-deterministic UI.
  await page.evaluate(() => {
    for (const animation of document.getAnimations({ subtree: true })) {
      if (animation.playState !== "running") continue;
      const timing = animation.effect?.getTiming();
      const duration = Number(timing?.duration);
      const iterations = Number(timing?.iterations);
      if (
        Number.isFinite(duration) &&
        Number.isFinite(iterations) &&
        iterations >= 0
      ) {
        animation.finish();
      }
    }
  });

  await expect
    .poll(
      () =>
        page.evaluate(() => {
          for (const animation of document.getAnimations({ subtree: true })) {
            if (animation.playState !== "running") continue;
            const timing = animation.effect?.getTiming();
            const duration = Number(timing?.duration);
            const iterations = Number(timing?.iterations);
            if (
              Number.isFinite(duration) &&
              Number.isFinite(iterations) &&
              iterations >= 0
            ) {
              animation.finish();
            }
          }

          return document
            .getAnimations({ subtree: true })
            .filter((animation) => animation.playState === "running")
            .filter((animation) => {
              const effect = animation.effect;
              const target =
                effect instanceof KeyframeEffect ? effect.target : null;
              if (!(target instanceof Element)) return true;

              const style = getComputedStyle(target);
              return (
                style.display !== "none" &&
                style.visibility !== "hidden" &&
                target.getClientRects().length > 0
              );
            })
            .map((animation) => {
              const effect = animation.effect;
              const target =
                effect instanceof KeyframeEffect ? effect.target : null;
              const timing = effect?.getTiming();
              return {
                animationName:
                  target instanceof Element
                    ? getComputedStyle(target).animationName
                    : "scripted",
                className:
                  target instanceof Element
                    ? (target.getAttribute("class") ?? "")
                    : "",
                duration: String(timing?.duration ?? "unknown"),
                iterations: timing?.iterations ?? 0,
                tagName: target instanceof Element ? target.tagName : "unknown",
              };
            });
        }),
      { message: `${label} running animations`, timeout: 5_000 },
    )
    .toEqual([]);
}
