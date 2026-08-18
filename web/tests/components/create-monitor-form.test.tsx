import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import React from "react";

const mutateMock = vi.fn();

vi.mock("@/hooks/use-monitors", () => ({
  useCreateMonitor: () => ({
    mutate: mutateMock,
    isPending: false,
  }),
}));

import { CreateMonitorForm } from "@/components/monitors/create-monitor-form";

describe("CreateMonitorForm", () => {
  beforeEach(() => {
    mutateMock.mockReset();
  });

  it("moves focus into the form when it opens", () => {
    render(<CreateMonitorForm onClose={vi.fn()} />);

    expect(screen.getByLabelText("Compound Name (optional)")).toHaveFocus();
  });

  it("keeps buyer-critical monitor actions at least 44px high", () => {
    render(<CreateMonitorForm onClose={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass(
      "min-h-11",
    );
    expect(
      screen.getByRole("button", { name: /^Create Monitor$/i }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", { name: "Close create monitor form" }),
    ).toHaveClass("h-11", "w-11");
  });

  it("prefills report context and submits a monitor", () => {
    const onClose = vi.fn();

    render(
      <CreateMonitorForm
        onClose={onClose}
        initialCompoundName="Aspirin"
        initialCompoundSmiles="CC(=O)Oc1ccccc1C(=O)O"
        initialSchedule="weekly"
        sourceContext={{
          analysisId: "analysis-9999",
          reportId: "report-1234",
          trustMode: "counsel",
          exportReady: true,
          routingModality: "small_molecule",
          routingUncertaintyCount: 1,
          claimArchetypes: ["composition"],
          doctrinePacks: ["us"],
        }}
      />,
    );

    expect(screen.getByDisplayValue("Aspirin")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("CC(=O)Oc1ccccc1C(=O)O"),
    ).toBeInTheDocument();
    expect(screen.getByText("Trust: Counsel")).toBeInTheDocument();
    expect(screen.getByText("Export ready")).toBeInTheDocument();
    expect(screen.getByText(/1 routing cautions/i)).toBeInTheDocument();
    expect(screen.getByText("composition")).toBeInTheDocument();
    expect(screen.getByText("us")).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("Aspirin"), {
      target: { value: "Updated Aspirin" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Create Monitor$/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      {
        analysis_id: "analysis-9999",
        compound_smiles: "CC(=O)Oc1ccccc1C(=O)O",
        compound_name: "Updated Aspirin",
        schedule: "weekly",
      },
      expect.any(Object),
    );

    const [, options] = mutateMock.mock.calls[0];
    act(() => {
      options?.onSuccess?.();
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows safe copy when monitor creation fails", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    render(
      <CreateMonitorForm
        onClose={vi.fn()}
        initialCompoundSmiles="CC(=O)Oc1ccccc1C(=O)O"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^Create Monitor$/i }));
    const [, options] = mutateMock.mock.calls[0];
    await act(async () => {
      options?.onError?.(new Error("database password leaked"));
    });

    expect(
      screen.getByText(
        "Monitor could not be created. Existing monitors are unchanged. Please retry.",
      ),
    ).toHaveAttribute("role", "alert");
    expect(consoleError).toHaveBeenCalledWith(
      "[CreateMonitorForm] Failed to create monitor",
    );
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        message: expect.stringMatching(/database password leaked/i),
      }),
    );
    expect(screen.getByLabelText("Compound SMILES")).not.toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(
      screen.queryByText(/database password leaked/i),
    ).not.toBeInTheDocument();
    consoleError.mockRestore();
  });

  it("locks monitor creation controls while the create request is pending", () => {
    render(
      <CreateMonitorForm
        onClose={vi.fn()}
        initialCompoundName="Aspirin"
        initialCompoundSmiles="CC(=O)Oc1ccccc1C(=O)O"
      />,
    );

    const nameInput = screen.getByLabelText("Compound Name (optional)");
    const smilesInput = screen.getByLabelText("Compound SMILES");
    const scheduleSelect = screen.getByLabelText("Schedule");
    const submitButton = screen.getByRole("button", {
      name: /^Create Monitor$/i,
    });

    fireEvent.click(submitButton);
    fireEvent.click(submitButton);

    expect(mutateMock).toHaveBeenCalledTimes(1);
    expect(nameInput).toBeDisabled();
    expect(smilesInput).toBeDisabled();
    expect(scheduleSelect).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Close create monitor form" }),
    ).toBeDisabled();
    expect(submitButton).toBeDisabled();
  });

  it("marks only the SMILES field invalid for missing SMILES", () => {
    render(<CreateMonitorForm onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /^Create Monitor$/i }));

    expect(screen.getByLabelText("Compound SMILES")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(
      screen.getByText(
        "Enter a compound SMILES string before creating a monitor.",
      ),
    ).toHaveAttribute("role", "alert");
    expect(mutateMock).not.toHaveBeenCalled();
  });

  it("allows analysis-seeded monitor creation without SMILES", () => {
    render(
      <CreateMonitorForm
        onClose={vi.fn()}
        initialCompoundName="Aspirin"
        sourceContext={{
          analysisId: "analysis-9999",
          reportId: "report-1234",
          trustMode: "counsel",
          exportReady: true,
        }}
      />,
    );

    expect(
      screen.getByText(
        "Praviar can resolve the monitored compound from the source report.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Create Monitor$/i }));

    expect(screen.getByLabelText("Compound SMILES")).not.toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(mutateMock).toHaveBeenCalledWith(
      {
        analysis_id: "analysis-9999",
        compound_smiles: undefined,
        compound_name: "Aspirin",
        schedule: "weekly",
      },
      expect.any(Object),
    );
  });
});
