import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const navigation = vi.hoisted(() => ({
  pathname: "/billing",
  search: "intent=credits&pack=portfolio_5",
}));
const retrySession = vi.hoisted(() => vi.fn());
const recovery = vi.hoisted(
  (): {
    reason: "expired" | "refresh_failed" | null;
    isRefreshing: boolean;
  } => ({
    reason: "expired",
    isRefreshing: false,
  }),
);

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthSessionRecovery: () => ({
    ...recovery,
    retrySession,
  }),
}));

import {
  buildSessionRecoverySignInHref,
  SESSION_RECOVERY_TITLE,
  SESSION_RECOVERY_UNCHANGED_COPY,
  SessionRecoveryBanner,
} from "@/components/auth/session-recovery-banner";

describe("SessionRecoveryBanner", () => {
  beforeEach(() => {
    navigation.pathname = "/billing";
    navigation.search = "intent=credits&pack=portfolio_5";
    recovery.reason = "expired";
    recovery.isRefreshing = false;
    retrySession.mockReset();
  });

  it("stays hidden outside durable recovery state", () => {
    recovery.reason = null;

    render(<SessionRecoveryBanner />);

    expect(
      screen.queryByTestId("session-recovery-banner"),
    ).not.toBeInTheDocument();
  });

  it("renders the exact persistent recovery copy and actions", () => {
    render(<SessionRecoveryBanner />);

    expect(screen.getByTestId("session-recovery-banner")).toHaveAttribute(
      "role",
      "alert",
    );
    expect(screen.getByText(SESSION_RECOVERY_TITLE)).toBeInTheDocument();
    expect(
      screen.getByText(SESSION_RECOVERY_UNCHANGED_COPY),
    ).toBeInTheDocument();

    const retryButton = screen.getByRole("button", { name: "Retry session" });
    expect(retryButton).toHaveClass("min-h-11");
    fireEvent.click(retryButton);
    expect(retrySession).toHaveBeenCalledTimes(1);

    expect(screen.getByRole("link", { name: "Sign in again" }))
      .toHaveClass("min-h-11")
      .toHaveAttribute(
        "href",
        "/sign-in?return_to=%2Fbilling%3Fintent%3Dcredits%26pack%3Dportfolio_5",
      );
  });

  it("keeps the recovery reason visible and disables retry while refreshing", () => {
    recovery.reason = "refresh_failed";
    recovery.isRefreshing = true;

    render(<SessionRecoveryBanner />);

    expect(screen.getByText(SESSION_RECOVERY_TITLE)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry session" }),
    ).toBeDisabled();
  });

  it("sanitizes the current path before constructing return_to", () => {
    expect(
      buildSessionRecoverySignInHref("//evil.example/account", "token=secret"),
    ).toBe("/sign-in?return_to=%2Fdashboard");
    expect(
      buildSessionRecoverySignInHref(
        "/analyses/ana-123/report",
        "?tab=evidence",
      ),
    ).toBe(
      "/sign-in?return_to=%2Fanalyses%2Fana-123%2Freport%3Ftab%3Devidence",
    );
  });
});
