import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { APIError } from "@/lib/api-client";
import { ExternalSharingPolicyCard } from "@/components/settings/external-sharing-policy-card";

const usePolicyMock = vi.hoisted(() => vi.fn());
const updatePolicyMutate = vi.hoisted(() => vi.fn());
const addToast = vi.hoisted(() => vi.fn());
const PROPOSAL_DIGEST = "d".repeat(64);

function destructivePreview(version: number, total = 2) {
  return {
    mode: "approved_domains_only",
    approved_domains: ["outside-counsel.example"],
    version,
    status: "confirmation_required",
    impact: {
      active_grant_count: Math.max(0, total - 1),
      pending_grant_count: total > 0 ? 1 : 0,
      total_grant_count: total,
    },
    proposal_digest: PROPOSAL_DIGEST,
    revoked_grant_count: 0,
  };
}

vi.mock("@/hooks/use-external-sharing-policy", () => ({
  useExternalSharingPolicy: () => usePolicyMock(),
  useUpdateExternalSharingPolicy: () => ({
    mutate: updatePolicyMutate,
    isPending: false,
  }),
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: () => ({ addToast }),
}));

describe("ExternalSharingPolicyCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePolicyMock.mockReturnValue({
      data: { mode: "open", approved_domains: [], version: 4 },
      error: null,
      isLoading: false,
      refetch: vi.fn(),
    });
  });

  it("makes the full policy option card the native radio target", () => {
    render(<ExternalSharingPolicyCard />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    const radios = screen.getAllByRole("radio");

    expect(radios).toHaveLength(2);
    for (const radio of radios) {
      expect(radio).toHaveClass("absolute", "inset-0", "h-full", "w-full");
      expect(radio.parentElement).toHaveClass("relative", "min-h-11");
      expect(
        radio.parentElement?.querySelector('[aria-hidden="true"]'),
      ).toBeInTheDocument();
    }
  });

  it("saves exact domains and reports automatic revocation honestly", async () => {
    let mutationCount = 0;
    updatePolicyMutate.mockImplementation(
      (payload: unknown, options: { onSuccess: (value: unknown) => void }) => {
        mutationCount += 1;
        options.onSuccess(
          mutationCount === 1
            ? destructivePreview(4)
            : {
                ...destructivePreview(5),
                status: "applied",
                proposal_digest: null,
                revoked_grant_count: 2,
              },
        );
        return payload;
      },
    );
    render(<ExternalSharingPolicyCard />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(
      screen.getByRole("radio", { name: /Approved exact domains only/i }),
    );
    fireEvent.change(screen.getByLabelText("Approved domains"), {
      target: { value: "outside-counsel.example" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Review and enforce policy" }),
    );
    expect(updatePolicyMutate).toHaveBeenNthCalledWith(
      1,
      {
        mode: "approved_domains_only",
        approved_domains: ["outside-counsel.example"],
        expected_version: 4,
        confirm_destructive: false,
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    expect(
      screen.getByText("Confirm destructive policy enforcement"),
    ).toBeInTheDocument();
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      /verification codes and access proofs invalidated/i,
    );
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      /exactly\s+1\s+active and\s+1\s+delivery-pending grants \(\s*2\s+total\)/,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm and enforce policy" }),
    );

    expect(updatePolicyMutate).toHaveBeenNthCalledWith(
      2,
      {
        mode: "approved_domains_only",
        approved_domains: ["outside-counsel.example"],
        expected_version: 4,
        confirm_destructive: true,
        proposal_digest: PROPOSAL_DIGEST,
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith(
        "External sharing policy enforced. 2 disallowed grants were revoked.",
        "success",
      ),
    );
    expect(
      screen.queryByText("Confirm destructive policy enforcement"),
    ).not.toBeInTheDocument();
  });

  it("refuses a success claim when applied impact and revocation counts disagree", () => {
    const refetch = vi.fn();
    usePolicyMock.mockReturnValue({
      data: { mode: "open", approved_domains: [], version: 4 },
      error: null,
      isLoading: false,
      refetch,
    });
    let mutationCount = 0;
    updatePolicyMutate.mockImplementation(
      (_payload: unknown, options: { onSuccess: (value: unknown) => void }) => {
        mutationCount += 1;
        options.onSuccess(
          mutationCount === 1
            ? destructivePreview(4)
            : {
                ...destructivePreview(5),
                status: "applied",
                proposal_digest: null,
                revoked_grant_count: 0,
              },
        );
      },
    );
    render(<ExternalSharingPolicyCard />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(
      screen.getByRole("radio", { name: /Approved exact domains only/i }),
    );
    fireEvent.change(screen.getByLabelText("Approved domains"), {
      target: { value: "outside-counsel.example" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Review and enforce policy" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm and enforce policy" }),
    );

    expect(refetch).toHaveBeenCalledTimes(1);
    expect(addToast).toHaveBeenCalledWith(
      expect.stringMatching(/inconsistent recipient-impact counts/i),
      "error",
    );
    expect(addToast).not.toHaveBeenCalledWith(
      expect.stringContaining("No active grants required revocation"),
      "success",
    );
  });

  it("rejects wildcard and suffix-style policy input before mutation", () => {
    render(<ExternalSharingPolicyCard />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(
      screen.getByRole("radio", { name: /Approved exact domains only/i }),
    );
    fireEvent.change(screen.getByLabelText("Approved domains"), {
      target: { value: "*.example.com" },
    });

    expect(
      screen.getByText(/is not an exact fully qualified domain/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Review and enforce policy" }),
    ).toBeDisabled();
    expect(updatePolicyMutate).not.toHaveBeenCalled();
  });

  it("states that an empty approved list is deny-all and revokes active grants", async () => {
    updatePolicyMutate.mockImplementation(
      (_payload: unknown, options: { onSuccess: (value: unknown) => void }) => {
        options.onSuccess({
          ...destructivePreview(4, 3),
          approved_domains: [],
        });
      },
    );
    render(<ExternalSharingPolicyCard />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(
      screen.getByRole("radio", { name: /Approved exact domains only/i }),
    );

    expect(
      screen.getByText(
        /blocks all new invitations and revokes every active external grant/i,
      ),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Review and enforce policy" }),
    );
    expect(
      screen.getByRole("button", { name: "Confirm and enforce policy" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cancel policy change" }),
    ).toHaveFocus();
    fireEvent.click(
      screen.getByRole("button", { name: "Cancel policy change" }),
    );
    expect(
      screen.queryByText("Confirm destructive policy enforcement"),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Review and enforce policy" }),
      ).toHaveFocus(),
    );
    expect(updatePolicyMutate).toHaveBeenCalledTimes(1);
  });

  it("hides cached policy controls at an authorization boundary", () => {
    usePolicyMock.mockReturnValue({
      data: {
        mode: "approved_domains_only",
        approved_domains: ["secret-counsel.example"],
        version: 9,
      },
      error: new APIError(403, "Forbidden"),
      isLoading: false,
      refetch: vi.fn(),
    });
    render(<ExternalSharingPolicyCard />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));

    expect(
      screen.getByText("External sharing policy restricted"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("secret-counsel.example"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("reloads instead of overwriting when admin A submits admin B's stale version", () => {
    const refetch = vi.fn();
    usePolicyMock.mockReturnValue({
      data: { mode: "open", approved_domains: [], version: 7 },
      error: null,
      isLoading: false,
      refetch,
    });
    let mutationCount = 0;
    updatePolicyMutate.mockImplementation(
      (
        _payload: unknown,
        options: {
          onSuccess: (value: unknown) => void;
          onError: (error: Error) => void;
        },
      ) => {
        mutationCount += 1;
        if (mutationCount === 1) {
          options.onSuccess({
            ...destructivePreview(7),
            approved_domains: [],
          });
        } else {
          options.onError(new APIError(409, "Policy version conflict"));
        }
      },
    );
    render(<ExternalSharingPolicyCard />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(
      screen.getByRole("radio", { name: /Approved exact domains only/i }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Review and enforce policy" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm and enforce policy" }),
    );

    expect(updatePolicyMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_version: 7,
        confirm_destructive: true,
        proposal_digest: PROPOSAL_DIGEST,
      }),
      expect.any(Object),
    );
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(addToast).toHaveBeenCalledWith(
      expect.stringMatching(/version or recipient impact changed/i),
      "error",
    );
    expect(
      screen.getByRole("radio", { name: /Any valid recipient domain/i }),
    ).toBeChecked();
  });

  it("treats a network mutation failure as unconfirmed and reloads authority", () => {
    const refetch = vi.fn();
    usePolicyMock.mockReturnValue({
      data: { mode: "open", approved_domains: [], version: 11 },
      error: null,
      isLoading: false,
      refetch,
    });
    updatePolicyMutate.mockImplementation(
      (_payload: unknown, options: { onError: (error: Error) => void }) => {
        options.onError(new Error("timeout after request write"));
      },
    );
    render(<ExternalSharingPolicyCard />);

    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.click(
      screen.getByRole("radio", { name: /Approved exact domains only/i }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Review and enforce policy" }),
    );
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(addToast).toHaveBeenCalledWith(
      "Policy update outcome could not be confirmed. The authoritative policy is being reloaded; review it before retrying.",
      "error",
    );
    expect(
      screen.queryByText(/recipient access are unchanged/i),
    ).not.toBeInTheDocument();
  });
});
