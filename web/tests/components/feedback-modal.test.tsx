import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { FeedbackModal } from "@/components/collaboration/feedback-modal";

// Mock dependencies
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "dev-token",
}));

const mockMutateAsync = vi.fn();
vi.mock("@/hooks/use-feedback", () => ({
  useSubmitFeedback: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
  // Re-export FeedbackPayload type (not needed at runtime, just for TS)
}));

const mockAddToast = vi.fn();
vi.mock("@/stores/toast-store", () => ({
  useToastStore: () => ({
    addToast: mockAddToast,
  }),
}));

describe("FeedbackModal", () => {
  const defaultProps = {
    analysisId: "analysis-123",
    patentId: "US12345678B2",
    currentRisk: "HIGH",
    open: true,
    onOpenChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("dialog rendering", () => {
    it("renders the dialog title when open", () => {
      render(<FeedbackModal {...defaultProps} />);
      expect(screen.getByText("Structured Feedback")).toBeInTheDocument();
    });

    it("renders the patent ID in the description", () => {
      render(<FeedbackModal {...defaultProps} />);
      expect(screen.getByText("US12345678B2")).toBeInTheDocument();
    });

    it("displays the current risk level on report tab", () => {
      render(<FeedbackModal {...defaultProps} />);
      expect(screen.getByText("HIGH")).toBeInTheDocument();
    });

    it("does not render dialog content when closed", () => {
      render(<FeedbackModal {...defaultProps} open={false} />);
      expect(screen.queryByText("Structured Feedback")).not.toBeInTheDocument();
    });

    it("limits report-level feedback to traceable report and text tabs", () => {
      render(<FeedbackModal {...defaultProps} patentId="" />);

      expect(
        screen.getByText(
          "Provide report-level feedback on this AI-assisted FTO assessment.",
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Report" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Text" })).toBeInTheDocument();
      expect(
        screen.queryByRole("tab", { name: "Patent" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("tab", { name: "Claim" }),
      ).not.toBeInTheDocument();
    });
  });

  describe("tab navigation", () => {
    it("renders all 4 feedback tabs", () => {
      render(<FeedbackModal {...defaultProps} />);
      expect(screen.getByText("Report")).toBeInTheDocument();
      expect(screen.getByText("Patent")).toBeInTheDocument();
      expect(screen.getByText("Claim")).toBeInTheDocument();
      expect(screen.getByText("Text")).toBeInTheDocument();
    });

    it("report tab is active by default", () => {
      render(<FeedbackModal {...defaultProps} />);
      const reportTab = screen.getByText("Report").closest("button")!;
      expect(reportTab.className).toContain("border-brand-primary");
    });

    it("clicking Patent tab shows patent-level form", () => {
      render(<FeedbackModal {...defaultProps} />);
      fireEvent.click(screen.getByText("Patent"));
      expect(screen.getByText("Issue Type")).toBeInTheDocument();
      expect(screen.getByText("Severity")).toBeInTheDocument();
    });

    it("clicking Claim tab shows claim-level form", () => {
      render(<FeedbackModal {...defaultProps} />);
      fireEvent.click(screen.getByText("Claim"));
      expect(screen.getByText("Claim Number")).toBeInTheDocument();
      expect(screen.getByText("Element Index")).toBeInTheDocument();
    });

    it("clicking Text tab shows text-level form", () => {
      render(<FeedbackModal {...defaultProps} />);
      fireEvent.click(screen.getByText("Text"));
      expect(screen.getByText("Section")).toBeInTheDocument();
      expect(screen.getByText("Annotation Type")).toBeInTheDocument();
    });

    it("implements roving keyboard tabs with labelled tabpanels", () => {
      render(<FeedbackModal {...defaultProps} />);

      const tablist = screen.getByRole("tablist", { name: "Feedback level" });
      const reportTab = screen.getByRole("tab", { name: "Report" });
      const patentTab = screen.getByRole("tab", { name: "Patent" });

      expect(tablist).toHaveClass("grid", "grid-cols-4");
      expect(reportTab).toHaveAttribute("tabindex", "0");
      expect(patentTab).toHaveAttribute("tabindex", "-1");

      fireEvent.keyDown(reportTab, { key: "ArrowRight" });

      expect(patentTab).toHaveAttribute("aria-selected", "true");
      expect(patentTab).toHaveAttribute("tabindex", "0");
      expect(screen.getByRole("tabpanel")).toHaveAttribute(
        "aria-labelledby",
        "feedback-tab-patent",
      );
    });
  });

  describe("thumbs up/down toggle", () => {
    it("renders Yes and No buttons", () => {
      render(<FeedbackModal {...defaultProps} />);
      expect(screen.getByText("Yes")).toBeInTheDocument();
      expect(screen.getByText("No")).toBeInTheDocument();
    });

    it("clicking Yes selects the thumbs up option", () => {
      render(<FeedbackModal {...defaultProps} />);
      const yesButton = screen.getByText("Yes").closest("button")!;
      fireEvent.click(yesButton);
      expect(yesButton.className).toContain("border-success");
    });

    it("clicking No selects the thumbs down option", () => {
      render(<FeedbackModal {...defaultProps} />);
      const noButton = screen.getByText("No").closest("button")!;
      fireEvent.click(noButton);
      expect(noButton.className).toContain("border-error");
    });

    it("shows corrected risk level options when No is selected", () => {
      render(<FeedbackModal {...defaultProps} />);
      expect(screen.queryByText("Correct risk level")).not.toBeInTheDocument();
      const noButton = screen.getByText("No").closest("button")!;
      fireEvent.click(noButton);
      expect(screen.getByText("Correct risk level")).toBeInTheDocument();
      expect(screen.getByText("MEDIUM")).toBeInTheDocument();
      expect(screen.getByText("LOW")).toBeInTheDocument();
      expect(screen.getByText("CLEAR")).toBeInTheDocument();
    });

    it("hides corrected risk level options when Yes is selected after No", () => {
      render(<FeedbackModal {...defaultProps} />);
      const noButton = screen.getByText("No").closest("button")!;
      fireEvent.click(noButton);
      expect(screen.getByText("Correct risk level")).toBeInTheDocument();
      const yesButton = screen.getByText("Yes").closest("button")!;
      fireEvent.click(yesButton);
      expect(screen.queryByText("Correct risk level")).not.toBeInTheDocument();
    });
  });

  describe("accuracy slider", () => {
    it("renders the accuracy slider with no default value", () => {
      render(<FeedbackModal {...defaultProps} />);
      expect(screen.getByText("\u2014")).toBeInTheDocument();
      expect(screen.getByText("Overall AI accuracy")).toBeInTheDocument();
    });

    it("renders the range input element", () => {
      render(<FeedbackModal {...defaultProps} />);
      const slider = screen.getByRole("slider");
      expect(slider).toBeInTheDocument();
      expect(slider).toHaveAttribute("min", "0");
      expect(slider).toHaveAttribute("max", "100");
      expect(slider).toHaveAttribute("step", "5");
      expect(slider).toHaveAccessibleName("Overall AI accuracy");
    });

    it("updates displayed percentage when slider changes", () => {
      render(<FeedbackModal {...defaultProps} />);
      const slider = screen.getByRole("slider");
      fireEvent.change(slider, { target: { value: "60" } });
      expect(screen.getByText("60%")).toBeInTheDocument();
    });
  });

  describe("notes textarea", () => {
    it("renders the notes textarea on report tab", () => {
      render(<FeedbackModal {...defaultProps} />);
      const textarea = screen.getByPlaceholderText(/General comments/);
      expect(textarea).toBeInTheDocument();
      expect(textarea).toHaveAccessibleName("Notes");
    });

    it("allows typing in the textarea", () => {
      render(<FeedbackModal {...defaultProps} />);
      const textarea = screen.getByPlaceholderText(
        /General comments/,
      ) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "This is wrong" } });
      expect(textarea.value).toBe("This is wrong");
    });
  });

  describe("submit button", () => {
    it("requires the API-mandated report assessment before submission", () => {
      render(<FeedbackModal {...defaultProps} />);
      const submitButton = screen
        .getByText("Submit Feedback")
        .closest("button")!;
      expect(submitButton).toBeDisabled();
      expect(
        screen.getByText(/Complete the overall risk decision/i),
      ).toBeInTheDocument();

      fireEvent.click(screen.getByText("Yes"));
      fireEvent.change(screen.getByRole("slider"), {
        target: { value: "75" },
      });

      expect(submitButton).toBeEnabled();
    });
  });

  describe("cancel button", () => {
    it("renders the Cancel button", () => {
      render(<FeedbackModal {...defaultProps} />);
      expect(screen.getByText("Cancel")).toBeInTheDocument();
    });

    it("calls onOpenChange(false) when Cancel is clicked", () => {
      const onOpenChange = vi.fn();
      render(<FeedbackModal {...defaultProps} onOpenChange={onOpenChange} />);
      fireEvent.click(screen.getByText("Cancel"));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  describe("submit flow", () => {
    it("calls mutateAsync with correct payload on submit", async () => {
      mockMutateAsync.mockResolvedValue({});
      render(<FeedbackModal {...defaultProps} />);

      // Select Yes
      const yesButton = screen.getByText("Yes").closest("button")!;
      fireEvent.click(yesButton);

      // Set accuracy
      const slider = screen.getByRole("slider");
      fireEvent.change(slider, { target: { value: "75" } });

      // Submit
      const submitButton = screen
        .getByText("Submit Feedback")
        .closest("button")!;
      await act(async () => {
        fireEvent.click(submitButton);
      });

      expect(mockMutateAsync).toHaveBeenCalledWith({
        analysis_id: "analysis-123",
        risk_level_correct: true,
        overall_accuracy: 0.75,
        corrections: [],
      });
    });

    it("serializes all four feedback levels into the API-supported corrections contract", async () => {
      mockMutateAsync.mockResolvedValue({});
      render(<FeedbackModal {...defaultProps} />);

      fireEvent.click(screen.getByRole("button", { name: "No" }));
      fireEvent.click(screen.getByRole("button", { name: "LOW" }));
      fireEvent.change(screen.getByRole("slider"), {
        target: { value: "65" },
      });
      fireEvent.change(screen.getByLabelText("Notes"), {
        target: { value: "Overall rationale" },
      });

      fireEvent.click(screen.getByRole("tab", { name: "Patent" }));
      fireEvent.change(screen.getByLabelText("Issue Type"), {
        target: { value: "wrong_risk" },
      });
      fireEvent.click(screen.getByRole("button", { name: "critical" }));
      fireEvent.change(screen.getByLabelText("Original Value"), {
        target: { value: "HIGH" },
      });
      fireEvent.change(screen.getByLabelText("Corrected Value"), {
        target: { value: "LOW" },
      });
      fireEvent.change(screen.getByLabelText("Reasoning"), {
        target: { value: "Claim scope is narrower." },
      });

      fireEvent.click(screen.getByRole("tab", { name: "Claim" }));
      fireEvent.change(screen.getByLabelText("Claim Number"), {
        target: { value: "7" },
      });
      fireEvent.change(screen.getByLabelText("Element Index"), {
        target: { value: "2" },
      });
      fireEvent.click(screen.getByRole("button", { name: "No" }));
      fireEvent.change(screen.getByLabelText("Corrected Mapping"), {
        target: { value: "not_met" },
      });
      fireEvent.change(screen.getByLabelText("Notes"), {
        target: { value: "Element is absent." },
      });

      fireEvent.click(screen.getByRole("tab", { name: "Text" }));
      fireEvent.change(screen.getByLabelText("Text Span"), {
        target: { value: "Overstated sentence" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Misleading" }));
      fireEvent.change(screen.getByLabelText("Correction"), {
        target: { value: "Qualified sentence" },
      });

      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", { name: "Submit Feedback" }),
        );
      });

      expect(mockMutateAsync).toHaveBeenCalledWith({
        analysis_id: "analysis-123",
        overall_accuracy: 0.65,
        risk_level_correct: false,
        corrected_risk: "LOW",
        corrections: [
          {
            patent_id: "US12345678B2",
            field: "report_notes",
            original_value: "",
            corrected_value: "",
            notes: "Overall rationale",
          },
          {
            patent_id: "US12345678B2",
            field: "patent:wrong_risk:critical",
            original_value: "HIGH",
            corrected_value: "LOW",
            notes: "Claim scope is narrower.",
          },
          {
            patent_id: "US12345678B2",
            field: "claim:7:element:2:mapping:incorrect",
            original_value: "",
            corrected_value: "not_met",
            notes: "Element is absent.",
          },
          {
            patent_id: "US12345678B2",
            field: "text:executive_summary:misleading",
            original_value: "Overstated sentence",
            corrected_value: "Qualified sentence",
            notes: "",
          },
        ],
      });
    });

    it("shows success toast after successful submission", async () => {
      mockMutateAsync.mockResolvedValue({});
      const onOpenChange = vi.fn();
      render(<FeedbackModal {...defaultProps} onOpenChange={onOpenChange} />);

      const yesButton = screen.getByText("Yes").closest("button")!;
      fireEvent.click(yesButton);

      const slider = screen.getByRole("slider");
      fireEvent.change(slider, { target: { value: "80" } });

      const submitButton = screen
        .getByText("Submit Feedback")
        .closest("button")!;
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await vi.waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          "Feedback submitted successfully",
          "success",
        );
      });

      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it("resets to the report tab after a successful submission", async () => {
      mockMutateAsync.mockResolvedValue({});
      const onOpenChange = vi.fn();
      const { rerender } = render(
        <FeedbackModal {...defaultProps} onOpenChange={onOpenChange} />,
      );

      fireEvent.click(screen.getByText("Yes"));
      fireEvent.change(screen.getByRole("slider"), {
        target: { value: "80" },
      });
      fireEvent.click(screen.getByText("Patent"));
      expect(screen.getByText("Issue Type")).toBeInTheDocument();

      const submitButton = screen
        .getByText("Submit Feedback")
        .closest("button")!;
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await vi.waitFor(() => {
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });

      rerender(
        <FeedbackModal
          {...defaultProps}
          open={false}
          onOpenChange={onOpenChange}
        />,
      );
      rerender(
        <FeedbackModal
          {...defaultProps}
          open={true}
          onOpenChange={onOpenChange}
        />,
      );

      expect(screen.getByText("Report").closest("button")!).toHaveClass(
        "border-brand-primary",
      );
      expect(screen.queryByText("Issue Type")).not.toBeInTheDocument();
    });
  });

  describe("patent-level feedback", () => {
    it("issue type dropdown has all 9 options", () => {
      render(<FeedbackModal {...defaultProps} />);
      fireEvent.click(screen.getByText("Patent"));
      const select = screen.getByRole("combobox") as HTMLSelectElement;
      // 1 placeholder + 9 issue types = 10 options
      expect(select.options.length).toBe(10);
    });

    it("severity buttons are rendered", () => {
      render(<FeedbackModal {...defaultProps} />);
      fireEvent.click(screen.getByText("Patent"));
      expect(screen.getByText("critical")).toBeInTheDocument();
      expect(screen.getByText("major")).toBeInTheDocument();
      expect(screen.getByText("minor")).toBeInTheDocument();
    });

    it("preserves full button geometry for selected severity states", () => {
      render(<FeedbackModal {...defaultProps} />);
      fireEvent.click(screen.getByText("Patent"));
      const critical = screen.getByRole("button", { name: "critical" });
      fireEvent.click(critical);

      expect(critical).toHaveClass(
        "rounded-lg",
        "border",
        "py-2",
        "border-error",
      );
      expect(critical).toHaveAttribute("aria-pressed", "true");
    });

    it("associates every patent field label with its control", () => {
      render(<FeedbackModal {...defaultProps} />);
      fireEvent.click(screen.getByText("Patent"));

      expect(screen.getByLabelText("Issue Type")).toBeInTheDocument();
      expect(screen.getByLabelText("Original Value")).toBeInTheDocument();
      expect(screen.getByLabelText("Corrected Value")).toBeInTheDocument();
      expect(screen.getByLabelText("Reasoning")).toBeInTheDocument();
    });
  });

  describe("claim and text accessibility", () => {
    it("associates claim feedback labels with their controls", () => {
      render(<FeedbackModal {...defaultProps} />);
      fireEvent.click(screen.getByText("Claim"));

      expect(screen.getByLabelText("Claim Number")).toBeInTheDocument();
      expect(screen.getByLabelText("Element Index")).toBeInTheDocument();
      expect(screen.getByLabelText("Notes")).toBeInTheDocument();
    });

    it("keeps selected text annotation buttons fully styled and labelled", () => {
      render(<FeedbackModal {...defaultProps} />);
      fireEvent.click(screen.getByText("Text"));

      expect(screen.getByLabelText("Section")).toBeInTheDocument();
      expect(screen.getByLabelText("Text Span")).toBeInTheDocument();
      const misleading = screen.getByRole("button", { name: "Misleading" });
      fireEvent.click(misleading);
      expect(misleading).toHaveClass(
        "rounded-lg",
        "border",
        "px-3",
        "border-warning",
      );
      expect(misleading).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByLabelText("Correction")).toBeInTheDocument();
    });
  });
});
