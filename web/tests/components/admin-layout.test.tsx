import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockUseAuth = vi.hoisted(() => vi.fn());
const mockReplace = vi.hoisted(() => vi.fn());
const principalState = vi.hoisted(() => ({
  available: true,
  canViewPlatformAdmin: true,
  refetch: vi.fn(),
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "token",
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: principalState.available
      ? {
          can_view_platform_admin: principalState.canViewPlatformAdmin,
        }
      : undefined,
    isFetching: false,
    isLoading: false,
    refetch: principalState.refetch,
  }),
}));

vi.mock("@/components/layout/sidebar-constants", async () => {
  const actual = await vi.importActual<
    typeof import("@/components/layout/sidebar-constants")
  >("@/components/layout/sidebar-constants");
  return {
    ...actual,
    hasClerk: true,
  };
});

import AdminLayout from "@/app/(dashboard)/admin/layout";

describe("AdminLayout", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockReplace.mockReset();
    principalState.available = true;
    principalState.canViewPlatformAdmin = true;
    principalState.refetch.mockReset();
  });

  it("renders a governed admin status while Clerk access is loading", () => {
    mockUseAuth.mockReturnValue({ isLoaded: false, orgRole: null });

    render(
      <AdminLayout>
        <div>Secret admin controls</div>
      </AdminLayout>,
    );

    expect(
      screen.getByTestId("admin-overview-status-auth"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Secret admin controls")).not.toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("keeps admin children and pending admin copy hidden while redirecting non-admin users", () => {
    mockUseAuth.mockReturnValue({ isLoaded: true, orgRole: "org:member" });

    render(
      <AdminLayout>
        <div>Secret admin controls</div>
      </AdminLayout>,
    );

    expect(screen.getByTestId("admin-redirecting-status")).toHaveTextContent(
      "Redirecting to dashboard",
    );
    expect(
      screen.queryByTestId("admin-overview-status-auth"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Confirming administrator access"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Secret admin controls")).not.toBeInTheDocument();
    expect(mockReplace).toHaveBeenCalledWith("/dashboard");
  });

  it("renders admin children only after admin access is confirmed", () => {
    mockUseAuth.mockReturnValue({ isLoaded: true, orgRole: "org:admin" });

    render(
      <AdminLayout>
        <div>Secret admin controls</div>
      </AdminLayout>,
    );

    expect(screen.getByText("Secret admin controls")).toBeInTheDocument();
    expect(
      screen.queryByTestId("admin-overview-status-auth"),
    ).not.toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("requires application-admin authority even for a Clerk organization admin", () => {
    mockUseAuth.mockReturnValue({ isLoaded: true, orgRole: "org:admin" });
    principalState.canViewPlatformAdmin = false;

    render(
      <AdminLayout>
        <div>Secret admin controls</div>
      </AdminLayout>,
    );

    expect(
      screen.getByRole("heading", {
        name: "Platform admin access restricted",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Secret admin controls")).not.toBeInTheDocument();
  });

  it("does not mislabel an unavailable capability snapshot as a role denial", () => {
    mockUseAuth.mockReturnValue({ isLoaded: true, orgRole: "org:admin" });
    principalState.available = false;

    render(
      <AdminLayout>
        <div>Secret admin controls</div>
      </AdminLayout>,
    );

    expect(
      screen.getByRole("heading", {
        name: "Platform admin access check unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "Platform admin access restricted",
      }),
    ).not.toBeInTheDocument();
  });
});
