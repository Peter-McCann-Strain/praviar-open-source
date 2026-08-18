import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const requestVerification = vi.fn();
const verifyRecipient = vi.fn();

vi.mock("@/app/share/[token]/actions", () => ({
  requestSharedReportVerification: (...args: unknown[]) =>
    requestVerification(...args),
  verifySharedReportRecipient: (...args: unknown[]) => verifyRecipient(...args),
}));

import { ShareVerificationPrompt } from "@/app/share/[token]/share-verification-prompt";

describe("ShareVerificationPrompt", () => {
  beforeEach(() => vi.clearAllMocks());

  it("does not disclose a recipient identity before proof", () => {
    render(<ShareVerificationPrompt token={"T".repeat(43)} />);
    expect(
      screen.getByRole("heading", { name: "Verify intended recipient" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Link received")).toBeInTheDocument();
    expect(screen.getByText("Recipient check required")).toBeInTheDocument();
    for (const step of screen.getAllByRole("listitem")) {
      expect(step).toHaveAttribute(
        "data-praviar-share-access-step-state",
        "pending",
      );
    }
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("8-digit verification code"),
    ).not.toBeInTheDocument();
    expect(
      screen
        .getByText("Recipient-bound access")
        .closest(".praviar-glass-strip"),
    ).toHaveClass("order-1", "lg:order-2");
  });

  it("labels and displays the synthetic-only demo code", async () => {
    requestVerification.mockResolvedValue({
      status: "sent",
      syntheticDemoCode: "24681357",
    });
    render(<ShareVerificationPrompt token={"T".repeat(43)} />);

    fireEvent.click(
      screen.getByRole("button", { name: "Send verification code" }),
    );

    expect(await screen.findByText("Synthetic demo only")).toBeInTheDocument();
    expect(screen.getByText("24681357")).toBeInTheDocument();
    expect(screen.getByLabelText("8-digit verification code")).toHaveAttribute(
      "autocomplete",
      "one-time-code",
    );
    expect(screen.getByRole("button", { name: "Send a new code" })).toHaveClass(
      "min-h-11",
    );
  });

  it("submits exactly eight digits and returns the attributed report", async () => {
    const onResultChange = vi.fn();
    requestVerification.mockResolvedValue({ status: "sent" });
    verifyRecipient.mockResolvedValue({
      status: "ok",
      report: {
        verified_recipient_email: "counsel@example.com",
        attributable_view_number: 2,
      },
    });
    render(
      <ShareVerificationPrompt
        token={"T".repeat(43)}
        onResultChange={onResultChange}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification code" }),
    );
    const input = await screen.findByLabelText("8-digit verification code");
    fireEvent.change(input, { target: { value: "24a6813579" } });
    expect(input).toHaveValue("24681357");
    fireEvent.click(
      screen.getByRole("button", { name: "Verify and view report" }),
    );

    await waitFor(() => {
      expect(verifyRecipient).toHaveBeenCalledWith("T".repeat(43), "24681357");
      expect(onResultChange).toHaveBeenCalledWith(
        expect.objectContaining({ status: "ok" }),
      );
    });
  });

  it("keeps code entry available when another send is rate limited", async () => {
    requestVerification.mockResolvedValue({ status: "rate-limited" });
    render(<ShareVerificationPrompt token={"T".repeat(43)} />);

    fireEvent.click(
      screen.getByRole("button", { name: "Send verification code" }),
    );

    expect(
      await screen.findByText(
        "A code was recently sent. Enter the code you already received, or wait before requesting another.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("8-digit verification code"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Verify and view report" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Send a new code" }),
    ).toBeInTheDocument();
  });

  it("focuses a rejected code without discarding the surrounding access context", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    requestVerification.mockResolvedValue({
      status: "sent",
      syntheticDemoCode: "24681357",
    });
    verifyRecipient.mockResolvedValue({
      status: "verification-required",
      invalid: true,
    });
    render(<ShareVerificationPrompt token={"T".repeat(43)} />);

    fireEvent.click(
      screen.getByRole("button", { name: "Send verification code" }),
    );
    const input = await screen.findByLabelText("8-digit verification code");
    fireEvent.change(input, { target: { value: "24681357" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Verify and view report" }),
    );

    const alert = await screen.findByRole("alert");
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
    expect(scrollIntoView).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Verify and view report" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Send a new code" }),
    ).toBeInTheDocument();
  });

  it("renders immediate recovery controls for an initially rejected code", async () => {
    render(<ShareVerificationPrompt token={"T".repeat(43)} initialInvalid />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(
      "That code is invalid, expired, or already used.",
    );
    expect(
      screen.getAllByText("That code is invalid, expired, or already used."),
    ).toHaveLength(1);
    expect(screen.getByLabelText("8-digit verification code")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Verify and view report" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Send a new code" }),
    ).toBeVisible();
    await waitFor(() => expect(alert).toHaveFocus());
  });
});
