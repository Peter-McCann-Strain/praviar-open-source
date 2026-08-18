import { fireEvent, render, screen } from "@testing-library/react";
import React, { createContext, useContext, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Notification,
  NotificationListResponse,
  UnreadCountResponse,
} from "@/hooks/use-notifications";

const mockPush = vi.fn();
const mockUseAuthToken = vi.fn();
const mockUseUnreadCount = vi.fn();
const mockUseNotifications = vi.fn();
const mockResolveActionMutate = vi.fn();
const mockDismissAllMutate = vi.fn();
const mockAddToast = vi.fn();
const principalState = vi.hoisted(() => ({
  role: "attorney",
  riskRatingsRestricted: false,
  canViewBilling: true,
  canViewPlatformAdmin: false,
  isError: false,
}));
const resolveState = vi.hoisted(() => ({
  isPending: false,
  variables: null as Notification | null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));

vi.mock("@radix-ui/react-popover", () => {
  const PopoverContext = createContext<{
    open: boolean;
    setOpen: (open: boolean) => void;
  }>({
    open: false,
    setOpen: () => {},
  });

  function Root({
    open,
    onOpenChange,
    children,
  }: {
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
    children: React.ReactNode;
  }) {
    const [internalOpen, setInternalOpen] = useState(false);
    const resolvedOpen = open ?? internalOpen;
    const setOpen = onOpenChange ?? setInternalOpen;

    return (
      <PopoverContext.Provider value={{ open: resolvedOpen, setOpen }}>
        {children}
      </PopoverContext.Provider>
    );
  }

  function Trigger({
    asChild,
    children,
  }: {
    asChild?: boolean;
    children: React.ReactElement;
  }) {
    const { open, setOpen } = useContext(PopoverContext);

    if (asChild) {
      return React.cloneElement(children, {
        onClick: () => setOpen(!open),
      });
    }

    return <button onClick={() => setOpen(!open)}>{children}</button>;
  }

  function Portal({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
  }

  function Content({
    children,
    className,
    "aria-labelledby": ariaLabelledBy,
  }: {
    children: React.ReactNode;
    className?: string;
    align?: string;
    "aria-labelledby"?: string;
    collisionPadding?: number;
    sideOffset?: number;
  }) {
    const { open } = useContext(PopoverContext);
    if (!open) return null;
    return (
      <div role="dialog" className={className} aria-labelledby={ariaLabelledBy}>
        {children}
      </div>
    );
  }

  return { Root, Trigger, Portal, Content };
});

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: (
    selector: (state: { addToast: typeof mockAddToast }) => unknown,
  ) => selector({ addToast: mockAddToast }),
}));

vi.mock("@/hooks/use-notifications", () => ({
  useUnreadCount: (...args: unknown[]) => mockUseUnreadCount(...args),
  useNotifications: (...args: unknown[]) => mockUseNotifications(...args),
  useResolveNotificationAction: () => ({
    mutate: mockResolveActionMutate,
    isPending: resolveState.isPending,
    variables: resolveState.variables,
  }),
  useDismissAll: () => ({ mutate: mockDismissAllMutate, isPending: false }),
}));

vi.mock("@/hooks/use-principal-capabilities", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-principal-capabilities")>();
  return {
    ...actual,
    usePrincipalCapabilities: () => ({
      data: {
        role: principalState.role,
        risk_ratings_restricted: principalState.riskRatingsRestricted,
        can_view_billing: principalState.canViewBilling,
        can_view_platform_admin: principalState.canViewPlatformAdmin,
      },
      isError: principalState.isError,
      isRefetchError: principalState.isError,
    }),
  };
});

import { NotificationBell } from "@/components/shared/notification-bell";

const now = new Date("2026-04-12T12:00:00.000Z").getTime();

const notifications: Notification[] = [
  {
    id: "n-1",
    type: "analysis_complete",
    title: "Analysis complete",
    body: "Your report is ready.",
    read: false,
    data: { analysis_id: "analysis-123" },
    created_at: new Date(now - 5 * 60_000).toISOString(),
  },
  {
    id: "n-2",
    type: "team_invite",
    title: "Team invite",
    body: "You were invited to a team.",
    read: true,
    data: { action: "manage_users" },
    created_at: new Date(now - 2 * 86_400_000).toISOString(),
  },
];

describe("NotificationBell", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(now);
    vi.clearAllMocks();
    principalState.role = "attorney";
    principalState.riskRatingsRestricted = false;
    principalState.canViewBilling = true;
    principalState.canViewPlatformAdmin = false;
    principalState.isError = false;
    resolveState.isPending = false;
    resolveState.variables = null;
    mockUseAuthToken.mockReturnValue("test-token");
    mockUseUnreadCount.mockReturnValue({
      data: { unread_count: 108 } satisfies UnreadCountResponse,
    });
    mockUseNotifications.mockReturnValue({
      data: {
        items: notifications,
        unread_count: 108,
        total: 2,
      } satisfies NotificationListResponse,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockResolveActionMutate.mockImplementation(
      (
        notification: Notification,
        options?: {
          onSuccess?: (result: {
            notification_id: string;
            actionable: boolean;
            destination: string | null;
            marked_read: boolean;
          }) => void;
          onSettled?: () => void;
        },
      ) => {
        const destination =
          notification.type === "team_invite"
            ? "/admin?tab=users"
            : "/analyses/analysis-123/report";
        options?.onSuccess?.({
          notification_id: notification.id,
          actionable: true,
          destination,
          marked_read: !notification.read,
        });
        options?.onSettled?.();
      },
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the unread badge, opens the panel, and dismisses all notifications", async () => {
    render(<NotificationBell />);

    const trigger = screen.getByRole("button", {
      name: "Notifications (108 unread)",
    });
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveClass("h-11", "w-11");
    expect(screen.getByText("99+")).toBeInTheDocument();

    fireEvent.click(trigger);

    expect(screen.getByRole("dialog")).toHaveClass(
      "w-[calc(100vw-1rem)]",
      "max-w-[380px]",
      "max-h-[calc(100dvh-1rem)]",
      "motion-reduce:animate-none",
      "motion-reduce:transition-none",
    );
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Notifications");
    expect(
      screen.getByRole("heading", { name: "Notifications" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark all read" })).toHaveClass(
      "focus-visible:ring-brand-primary/70",
    );
    expect(
      screen.getByRole("button", { name: "Notification Settings" }),
    ).toHaveClass("focus-visible:ring-brand-primary/70");
    expect(
      screen.getByRole("button", {
        name: /Analysis complete.*Unread notification/,
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(mockDismissAllMutate).toHaveBeenCalledTimes(1);
  });

  it("uses the server-authoritative resolver before navigating", () => {
    render(<NotificationBell />);

    fireEvent.click(
      screen.getByRole("button", { name: "Notifications (108 unread)" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /^Analysis complete / }),
    );

    expect(mockResolveActionMutate).toHaveBeenCalledWith(
      notifications[0],
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    expect(mockPush).toHaveBeenCalledWith("/analyses/analysis-123/report");
  });

  it("routes team invitations to the admin users surface", () => {
    principalState.role = "admin";
    principalState.canViewPlatformAdmin = true;
    render(<NotificationBell />);

    fireEvent.click(
      screen.getByRole("button", { name: "Notifications (108 unread)" }),
    );
    fireEvent.click(screen.getByRole("button", { name: /^Team invite / }));

    expect(mockResolveActionMutate).toHaveBeenCalledWith(
      notifications[1],
      expect.any(Object),
    );
    expect(mockPush).toHaveBeenCalledWith("/admin?tab=users");
  });

  it("does not navigate or mark read while current authority is unavailable", () => {
    principalState.isError = true;
    render(<NotificationBell />);

    fireEvent.click(
      screen.getByRole("button", { name: "Notifications (108 unread)" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /^Analysis complete / }),
    );

    expect(mockResolveActionMutate).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
    expect(mockAddToast).toHaveBeenCalledWith(
      "Notification access check unavailable. Retry after role authority refreshes.",
      "warning",
    );
  });

  it("keeps the bell open when the server says access changed", () => {
    mockResolveActionMutate.mockImplementation(
      (_notification: Notification, options?: { onError?: () => void }) => {
        options?.onError?.();
      },
    );
    render(<NotificationBell />);

    fireEvent.click(
      screen.getByRole("button", { name: "Notifications (108 unread)" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /^Analysis complete / }),
    );

    expect(mockPush).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(mockAddToast).toHaveBeenCalledWith(
      "Access to this notification changed or could not be re-verified. No restricted destination was opened.",
      "warning",
    );
  });

  it("renders tombstoned rows as non-action content", () => {
    mockUseNotifications.mockReturnValue({
      data: {
        items: [
          {
            ...notifications[0],
            id: "n-tombstone",
            title: "Access to this item changed",
            body: "This notification is no longer available.",
            actionable: false,
            tombstoned: true,
          },
        ],
        unread_count: 1,
        total: 1,
      } satisfies NotificationListResponse,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    render(<NotificationBell />);

    fireEvent.click(
      screen.getByRole("button", { name: "Notifications (108 unread)" }),
    );

    expect(
      screen.queryByRole("button", {
        name: /Access to this item changed/,
      }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Access changed")).toBeInTheDocument();
    expect(mockResolveActionMutate).not.toHaveBeenCalled();
  });

  it("shows a retry state instead of a false empty state on fetch failure", () => {
    const refetch = vi.fn();
    mockUseNotifications.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("offline"),
      refetch,
    });
    render(<NotificationBell />);

    fireEvent.click(
      screen.getByRole("button", { name: "Notifications (108 unread)" }),
    );

    expect(screen.getByText("Notifications unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No notifications")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Retry notifications" }),
    );
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("uses the loaded notification total when the count request is unavailable", () => {
    mockUseUnreadCount.mockReturnValue({
      data: undefined,
      error: new Error("count unavailable"),
    });
    mockUseNotifications.mockReturnValue({
      data: {
        items: notifications,
        unread_count: 7,
        total: 2,
      } satisfies NotificationListResponse,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<NotificationBell />);

    expect(
      screen.getByRole("button", { name: "Notifications (7 unread)" }),
    ).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("disables a notification while its action is resolving", () => {
    resolveState.isPending = true;
    resolveState.variables = notifications[0];
    render(<NotificationBell />);

    fireEvent.click(
      screen.getByRole("button", { name: "Notifications (108 unread)" }),
    );

    expect(
      screen.getByRole("button", { name: /^Analysis complete / }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /^Team invite / }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Notification Settings" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Mark all read" }),
    ).toBeDisabled();
  });

  it("uses a synchronous guard against rapid duplicate activations", () => {
    mockResolveActionMutate.mockImplementation(() => undefined);
    render(<NotificationBell />);

    fireEvent.click(
      screen.getByRole("button", { name: "Notifications (108 unread)" }),
    );
    const notification = screen.getByRole("button", {
      name: /^Analysis complete /,
    });
    fireEvent.click(notification);
    fireEvent.click(notification);

    expect(mockResolveActionMutate).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state when there are no notifications", () => {
    mockUseUnreadCount.mockReturnValue({
      data: { unread_count: 0 } satisfies UnreadCountResponse,
    });
    mockUseNotifications.mockReturnValue({
      data: {
        items: [],
        unread_count: 0,
        total: 0,
      } satisfies NotificationListResponse,
      isLoading: false,
    });

    render(<NotificationBell />);
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));

    expect(screen.getByText("No notifications")).toBeInTheDocument();
    expect(screen.getByText("You're all caught up!")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Notification Settings" }),
    ).toHaveClass("focus-visible:ring-brand-primary/70");
  });

  it("shows a loading indicator before notifications resolve", () => {
    mockUseUnreadCount.mockReturnValue({
      data: { unread_count: 0 } satisfies UnreadCountResponse,
    });
    mockUseNotifications.mockReturnValue({
      data: {
        items: [],
        unread_count: 0,
        total: 0,
      } satisfies NotificationListResponse,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<NotificationBell />);
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));

    expect(
      screen.getByRole("status", { name: "Loading notifications" }),
    ).toBeInTheDocument();
  });
});
