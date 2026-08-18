import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ShareDialogHeader } from "@/components/collaboration/share-dialog-header";

vi.mock("@/components/brand/praviar-mark-frame", () => ({
  PraviarMarkFrame: () => <div aria-hidden="true" />,
}));

describe("ShareDialogHeader", () => {
  it("describes mailbox-bound invitation management and exposes a 44px close target", () => {
    const onClose = vi.fn();
    render(<ShareDialogHeader onClose={onClose} />);

    expect(
      screen.getByText(
        "Create and manage mailbox-bound invitations with evidence boundaries intact.",
      ),
    ).toHaveClass("hidden", "sm:block");
    expect(screen.getByText("Mailbox-bound · read-only evidence")).toHaveClass(
      "sm:hidden",
    );
    expect(screen.getByRole("heading", { level: 3 })).toHaveClass(
      "text-lg",
      "leading-6",
      "sm:type-heading-sm",
    );
    const close = screen.getByRole("button", { name: "Close share dialog" });
    expect(close).toHaveClass("h-11", "w-11");
    fireEvent.click(close);
    expect(onClose).toHaveBeenCalledOnce();
  });
});
