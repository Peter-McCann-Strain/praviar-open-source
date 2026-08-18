import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const clerkState = vi.hoisted(() => ({
  isLoaded: true,
  isSignedIn: true,
  orgId: null as string | null,
}));

const navigationState = vi.hoisted(() => ({
  pathname: "/dashboard",
  search: "",
}));

vi.mock("@/hooks/use-clerk-session", () => ({ hasClerk: true }));
vi.mock("next/navigation", () => ({
  usePathname: () => navigationState.pathname,
  useSearchParams: () => new URLSearchParams(navigationState.search),
}));
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => clerkState,
  UserButton: () => <button type="button">Account</button>,
  OrganizationSwitcher: (props: {
    hidePersonal?: boolean;
    afterSelectOrganizationUrl?: string;
  }) => (
    <button
      type="button"
      data-testid="organization-switcher"
      data-hide-personal={String(props.hidePersonal)}
      data-after-select={props.afterSelectOrganizationUrl}
    >
      Choose organization
    </button>
  ),
}));

import { OrganizationWorkspaceBoundary } from "@/components/auth/organization-workspace-boundary";

describe("OrganizationWorkspaceBoundary", () => {
  beforeEach(() => {
    clerkState.isLoaded = true;
    clerkState.isSignedIn = true;
    clerkState.orgId = null;
    navigationState.pathname = "/dashboard";
    navigationState.search = "";
  });

  it("locks private children until the user selects an active organization", () => {
    render(
      <OrganizationWorkspaceBoundary>
        <div>Private dashboard</div>
      </OrganizationWorkspaceBoundary>,
    );

    expect(
      screen.getByRole("heading", { name: "Select your organization" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Private dashboard")).not.toBeInTheDocument();
    const switcher = screen.getByTestId("organization-switcher");
    expect(switcher).toHaveAttribute("data-hide-personal", "true");
    expect(switcher).toHaveAttribute("data-after-select", "/dashboard");
  });

  it("mounts private children only for an explicit active organization", () => {
    clerkState.orgId = "org_buyer";
    render(
      <OrganizationWorkspaceBoundary>
        <div>Private dashboard</div>
      </OrganizationWorkspaceBoundary>,
    );

    expect(screen.getByText("Private dashboard")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Select your organization" }),
    ).not.toBeInTheDocument();
  });

  it("does not mount private children while Clerk is still resolving identity", () => {
    clerkState.isLoaded = false;
    render(
      <OrganizationWorkspaceBoundary>
        <div>Private dashboard</div>
      </OrganizationWorkspaceBoundary>,
    );

    expect(
      screen.getByText("Verifying your organization workspace…"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Private dashboard")).not.toBeInTheDocument();
  });

  it("renders session recovery instead of a blank app when Clerk resolves signed out", () => {
    clerkState.isSignedIn = false;
    navigationState.pathname = "/analyses/ana-123/report";
    navigationState.search = "tab=evidence";

    render(
      <OrganizationWorkspaceBoundary>
        <div>Private dashboard</div>
      </OrganizationWorkspaceBoundary>,
    );

    expect(
      screen.getByRole("heading", { name: "Your session expired" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Private dashboard")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute(
      "href",
      "/sign-in?return_to=%2Fanalyses%2Fana-123%2Freport%3Ftab%3Devidence",
    );
  });
});
