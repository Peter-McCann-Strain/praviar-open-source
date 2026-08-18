import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MutationRecoveryNotice } from "@/components/shared/mutation-recovery-notice";

describe("MutationRecoveryNotice", () => {
  it("renders an outcome-unknown recovery action with stable contracts", () => {
    const onAction = vi.fn();
    render(
      <MutationRecoveryNotice
        actionLabel="Refresh ledger"
        dataTestId="test-mutation-recovery"
        description="Refresh authoritative state before another mutation."
        mode="outcome-unknown"
        onAction={onAction}
        title="Outcome unconfirmed"
      />,
    );

    const notice = screen.getByTestId("test-mutation-recovery");
    expect(notice).toHaveAttribute(
      "data-mutation-recovery-mode",
      "outcome-unknown",
    );
    expect(notice).toHaveAttribute("role", "alert");
    const action = screen.getByTestId("test-mutation-recovery-action");
    expect(action).toHaveClass("min-h-11", "w-full", "sm:w-auto");
    fireEvent.click(action);
    expect(onAction).toHaveBeenCalledOnce();
  });

  it("supports an explicit failed-mode dismissal", () => {
    const onDismiss = vi.fn();
    render(
      <MutationRecoveryNotice
        actionLabel="Retry exact save"
        dataTestId="failed-mutation-recovery"
        description="The server rejected the save."
        dismissLabel="Keep editing"
        mode="failed"
        onAction={vi.fn()}
        onDismiss={onDismiss}
        title="Save failed"
      />,
    );

    expect(screen.getByTestId("failed-mutation-recovery")).toHaveAttribute(
      "data-mutation-recovery-mode",
      "failed",
    );
    fireEvent.click(screen.getByTestId("failed-mutation-recovery-dismiss"));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
