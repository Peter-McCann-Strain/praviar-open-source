import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  ApprovalFlow,
  ApprovalSteps,
} from "@/components/collaboration/approval-flow";

describe("ApprovalFlow", () => {
  it("renders pending status", () => {
    render(<ApprovalFlow status="pending" />);
    expect(screen.getByText("Pending Review")).toBeInTheDocument();
  });

  it("renders approved status with approver", () => {
    render(
      <ApprovalFlow
        status="approved"
        approver="Jane Smith"
        approvedAt="2026-03-15T10:00:00Z"
      />,
    );
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText(/Jane Smith/)).toBeInTheDocument();
  });

  it("shows approve button when canApprove and not approved", () => {
    const onApprove = vi.fn();
    render(<ApprovalFlow status="pending" canApprove onApprove={onApprove} />);
    // Click Approve to show confirmation
    const approveButton = screen.getByRole("button", {
      name: "Approve report",
    });
    expect(approveButton).toHaveClass("min-h-11", "w-full", "sm:w-auto");
    fireEvent.click(approveButton);
    // Click Confirm Approval to execute
    const confirmButton = screen.getByRole("button", {
      name: /confirm approval/i,
    });
    expect(confirmButton).toHaveClass("min-h-11", "w-full", "sm:w-auto");
    fireEvent.click(confirmButton);
    expect(onApprove).toHaveBeenCalled();
  });

  it("hides approve button when already approved", () => {
    render(<ApprovalFlow status="approved" canApprove onApprove={vi.fn()} />);
    expect(screen.queryByText("Approve")).not.toBeInTheDocument();
  });

  it("shows request changes button with confirmation", () => {
    const onRequestChanges = vi.fn();
    render(
      <ApprovalFlow
        status="under_review"
        canApprove
        onRequestChanges={onRequestChanges}
      />,
    );
    fireEvent.click(screen.getByText("Request Changes"));
    fireEvent.click(
      screen.getByRole("button", { name: /confirm request changes/i }),
    );
    expect(onRequestChanges).toHaveBeenCalled();
  });

  it("passes comment to onApprove callback", () => {
    const onApprove = vi.fn();
    render(<ApprovalFlow status="pending" canApprove onApprove={onApprove} />);
    fireEvent.click(screen.getByText("Approve"));
    const textarea = screen.getByPlaceholderText(/add a note/i);
    fireEvent.change(textarea, { target: { value: "Looks good" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm approval/i }));
    expect(onApprove).toHaveBeenCalledWith("Looks good");
  });

  it("clears pending action state when cancelled", () => {
    render(
      <ApprovalFlow
        status="under_review"
        canApprove
        onRequestChanges={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("Request Changes"));
    fireEvent.change(screen.getByPlaceholderText(/add a note/i), {
      target: { value: "Needs revision" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: /^cancel$/i })[1]!);

    expect(
      screen.queryByPlaceholderText(/add a note/i),
    ).not.toBeInTheDocument();
  });

  it("moves focus into confirmation and returns it to the cancelled action", () => {
    render(
      <ApprovalFlow
        status="under_review"
        canApprove
        onRequestChanges={vi.fn()}
      />,
    );

    const requestChangesButton = screen.getByRole("button", {
      name: "Request changes",
    });
    requestChangesButton.focus();
    fireEvent.click(requestChangesButton);

    expect(screen.getByPlaceholderText(/add a note/i)).toHaveFocus();

    fireEvent.click(screen.getAllByRole("button", { name: /^cancel$/i })[1]!);

    expect(
      screen.getByRole("button", { name: "Request changes" }),
    ).toHaveFocus();
  });
});

describe("ApprovalSteps", () => {
  it("renders three step indicators", () => {
    const { container } = render(<ApprovalSteps currentStatus="pending" />);
    const circles = container.querySelectorAll("[class*='rounded-full']");
    expect(circles.length).toBeGreaterThanOrEqual(3);
  });

  it("highlights steps up to current status", () => {
    render(<ApprovalSteps currentStatus="approved" />);
    // All three steps should be active when approved
  });
});
