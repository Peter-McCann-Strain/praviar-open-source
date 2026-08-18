import { render, screen } from "@testing-library/react";
import { act } from "react";
import { hydrateRoot, type Root } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DigestUnsubscribePage from "@/app/unsubscribe/digest/page";

const { cookiesMock } = vi.hoisted(() => ({
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: cookiesMock,
}));

async function renderPage(searchParams: { result?: string; token?: string }) {
  const page = await DigestUnsubscribePage({
    searchParams: Promise.resolve(searchParams),
  });
  return render(page);
}

describe("DigestUnsubscribePage", () => {
  beforeEach(() => {
    cookiesMock.mockResolvedValue({
      get: vi.fn(() => undefined),
    });
  });

  it("offers an explicit safe cancel beside the destructive confirmation", async () => {
    await renderPage({ token: "t".repeat(80) });

    expect(screen.getByTestId("digest-preference-surface")).toHaveClass(
      "max-w-4xl",
      "md:grid-cols-[0.82fr_1.18fr]",
    );
    expect(screen.getByTestId("digest-preference-context")).toHaveClass(
      "md:border-b-0",
      "md:border-r",
    );
    const preferenceContext = screen.getByTestId("digest-preference-context");
    expect(
      preferenceContext.querySelector("[data-praviar-mark]"),
    ).toBeVisible();
    expect(preferenceContext.querySelector("img")).toBeNull();
    expect(
      screen.getByRole("heading", {
        name: "Change one email stream. Keep the rest intact.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Alerts preserved")).toBeInTheDocument();
    expect(screen.getByText("Account unchanged")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Turn off weekly digests" }),
    ).toBeInTheDocument();
    const form = screen
      .getByRole("button", { name: "Turn off weekly digests" })
      .closest("form");
    expect(form).toHaveAttribute("action", "/api/email/unsubscribe");
    expect(form?.querySelector('input[name="token"]')).toBeNull();
    const cancel = screen.getByRole("link", { name: "Keep weekly digests" });
    expect(cancel).toHaveAttribute("href", "/");
    expect(cancel).toHaveClass("min-h-11");
    expect(cancel).toHaveClass("focus-visible:ring-2");
  });

  it("keeps result-state actions touch-sized and keyboard visible", async () => {
    await renderPage({ result: "processed" });

    expect(
      screen.getByRole("heading", { name: "Request received" }),
    ).toBeInTheDocument();
    for (const link of screen.getAllByRole("link")) {
      expect(link).toHaveClass("min-h-11");
      expect(link).toHaveClass("focus-visible:ring-2");
    }
  });

  it("uses the HttpOnly cookie without rendering the raw capability", async () => {
    const token = `du1.${"t".repeat(86)}`;
    cookiesMock.mockResolvedValue({
      get: vi.fn(() => ({ value: token })),
    });

    await renderPage({});

    expect(
      screen.getByRole("button", { name: "Turn off weekly digests" }),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(token);
    expect(document.querySelector(`input[value="${token}"]`)).toBeNull();
  });

  it("hydrates the capability-confirmation surface without attribute drift", async () => {
    const page = await DigestUnsubscribePage({
      searchParams: Promise.resolve({ token: "t".repeat(80) }),
    });
    const container = document.createElement("div");
    container.innerHTML = renderToString(page);
    document.body.append(container);
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    let root: Root | undefined;

    try {
      await act(async () => {
        root = hydrateRoot(container, page);
        await Promise.resolve();
      });

      expect(consoleError.mock.calls.flat().map(String).join("\n")).not.toMatch(
        /hydration|hydrated|didn't match/iu,
      );
    } finally {
      await act(async () => {
        root?.unmount();
      });
      consoleError.mockRestore();
      container.remove();
    }
  });
});
