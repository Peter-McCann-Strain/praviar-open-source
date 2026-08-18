import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BatchDetailPanel } from "@/components/batch/batch-detail-panel";
import { BatchPageHeader } from "@/components/batch/batch-page-header";
import { BatchPagination } from "@/components/batch/batch-pagination";
import { BatchSummaryCards } from "@/components/batch/batch-summary-cards";
import { BatchesTable } from "@/components/batch/batches-table";
import { CreateBatchForm } from "@/components/batch/create-batch-form";
import { relativeTime } from "@/components/batch/helpers";
import { APIError } from "@/lib/api-client";
import type { BatchResponse } from "@/hooks/use-batch";

const mockCreateMutate = vi.hoisted(() => vi.fn());
const mockUseBatch = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-batch", () => ({
  useBatch: mockUseBatch,
  useCreateBatch: () => ({
    mutate: mockCreateMutate,
    isPending: false,
  }),
}));

vi.mock("@/components/shared/animated-counter", () => ({
  AnimatedCounter: ({ value }: { value: number }) => <span>{value}</span>,
}));

vi.mock("@/components/shared/stagger-container", () => ({
  StaggerContainer: ({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) => <div className={className}>{children}</div>,
  StaggerItem: ({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) => <div className={className}>{children}</div>,
}));

const batches: BatchResponse[] = [
  {
    id: "batch-1",
    name: "Launch compounds",
    total_compounds: 6,
    completed_count: 4,
    failed_count: 1,
    status: "partial",
    analysis_ids: ["analysis-123456789"],
    created_at: "2026-05-26T11:30:00.000Z",
    updated_at: "2026-05-26T11:45:00.000Z",
  },
  {
    id: "batch-2",
    name: "Backlog triage",
    total_compounds: 2,
    completed_count: 1,
    failed_count: 0,
    status: "running",
    analysis_ids: [],
    created_at: "2026-05-25T12:00:00.000Z",
    updated_at: "2026-05-26T11:00:00.000Z",
  },
];

describe("batch helpers", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-26T12:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("formats relative times for fresh, minute, hour, and day ranges", () => {
    expect(relativeTime("2026-05-26T12:00:00.000Z")).toBe("just now");
    expect(relativeTime("2026-05-26T11:30:00.000Z")).toBe("30m ago");
    expect(relativeTime("2026-05-26T09:00:00.000Z")).toBe("3h ago");
    expect(relativeTime("2026-05-24T12:00:00.000Z")).toBe("2d ago");
  });
});

describe("batch dashboard components", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-26T12:00:00.000Z"));
    mockCreateMutate.mockReset();
    mockUseBatch.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("summarizes portfolio totals from batch data", () => {
    render(<BatchSummaryCards data={{ total: 2, items: batches }} />);

    expect(screen.getByText("Portfolio runs")).toBeInTheDocument();
    expect(screen.getByText("1 active")).toBeInTheDocument();
    expect(screen.getByText("Counsel handoff")).toBeInTheDocument();
    expect(screen.getByText("1 ready or partial")).toBeInTheDocument();
    expect(screen.getByText("Source coverage")).toBeInTheDocument();
    expect(screen.getByText("5 of 8 screened")).toHaveClass(
      "leading-5",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("Failure watch")).toBeInTheDocument();
    expect(screen.getByText("Needs operator review")).toHaveClass(
      "leading-5",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("Counsel handoff").closest(".grid")).toHaveClass(
      "grid-cols-2",
      "min-[1440px]:grid-cols-4",
    );
  });

  it("labels synthetic batch timestamps instead of presenting stale fixture age", () => {
    render(
      <BatchesTable
        items={[
          {
            ...batches[0],
            id: "batch_demo_001",
            updated_at: "2026-04-10T09:21:00.000Z",
          },
        ]}
        onOpenDetails={vi.fn()}
        onCancel={vi.fn()}
        cancelPending={false}
      />,
    );

    expect(screen.getByText("Synthetic fixture")).toBeInTheDocument();
    expect(screen.queryByText(/\d+d ago/)).not.toBeInTheDocument();
  });

  it("renders batch rows, report links, progress, and detail actions", () => {
    const onOpenDetails = vi.fn();
    render(
      <BatchesTable
        items={batches}
        onOpenDetails={onOpenDetails}
        onCancel={vi.fn()}
        cancelPending={false}
        currentUserRole="attorney"
        riskRatingsRestricted={false}
      />,
    );

    const firstRow = screen.getByText("Launch compounds").closest("tr");
    expect(firstRow).not.toBeNull();
    expect(screen.getByRole("table")).toHaveClass(
      "w-full",
      "min-[1440px]:min-w-[960px]",
    );
    expect(
      screen.getByLabelText("Search batch runs").closest(".grid"),
    ).toHaveClass("min-[1440px]:grid-cols-[minmax(0,1fr)_auto]");
    expect(within(firstRow!).getByText("partial")).toBeInTheDocument();
    expect(firstRow).toHaveTextContent("83%");
    expect(firstRow).toHaveTextContent("4/6");
    expect(within(firstRow!).getByText("(1F)")).toBeInTheDocument();
    expect(within(firstRow!).getByText("Watch")).toBeInTheDocument();
    expect(within(firstRow!).getByText("Counsel review")).toBeInTheDocument();
    expect(within(firstRow!).getByText("15m ago")).toBeInTheDocument();
    expect(
      within(firstRow!).getByRole("link", { name: /Open report/i }),
    ).toHaveAttribute(
      "href",
      "/analyses/analysis-123456789/report?audience=diligence&ai_context=review_questions&tab=claims",
    );
    expect(
      within(firstRow!).getByRole("link", { name: /Open report/i }),
    ).toHaveClass("min-h-11", "w-full", "sm:w-auto");

    const secondRow = screen.getByText("Backlog triage").closest("tr");
    expect(secondRow).not.toBeNull();
    expect(
      within(secondRow!).queryByRole("link", { name: /Open report/i }),
    ).not.toBeInTheDocument();

    const detailsButton = within(secondRow!).getByRole("button", {
      name: /Details/i,
    });
    expect(detailsButton).toHaveClass("min-h-11", "w-full", "sm:w-auto");
    fireEvent.click(detailsButton);
    expect(onOpenDetails).toHaveBeenCalledWith({
      id: "batch-2",
      name: "Backlog triage",
    });

    const attentionFilter = screen.getByRole("button", {
      name: "Needs attention",
    });
    expect(attentionFilter).toHaveClass("min-h-11");
    fireEvent.click(attentionFilter);
    expect(screen.getByText("Launch compounds")).toBeInTheDocument();
    expect(screen.queryByText("Backlog triage")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All batches" }));
    fireEvent.change(screen.getByLabelText("Search batch runs"), {
      target: { value: "Backlog" },
    });
    expect(screen.queryByText("Launch compounds")).not.toBeInTheDocument();
    expect(screen.getByText("Backlog triage")).toBeInTheDocument();
  });

  it.each([
    {
      role: "scientist",
      riskRatingsRestricted: true,
      label: "Open summary",
      href: "/analyses/analysis-123456789/report/summary",
    },
    {
      role: "scientist",
      riskRatingsRestricted: false,
      label: "Open report",
      href: "/analyses/analysis-123456789/report?audience=diligence&ai_context=review_questions&tab=claims",
    },
    {
      role: "client",
      riskRatingsRestricted: false,
      label: "Open summary",
      href: "/analyses/analysis-123456789/report/summary",
    },
    {
      role: "attorney",
      riskRatingsRestricted: true,
      label: "Open report",
      href: "/analyses/analysis-123456789/report?audience=diligence&ai_context=review_questions&tab=claims",
    },
  ])(
    "routes $role batch handoffs to the authorized report surface",
    ({ role, riskRatingsRestricted, label, href }) => {
      render(
        <BatchesTable
          items={[batches[0]]}
          onOpenDetails={vi.fn()}
          onCancel={vi.fn()}
          cancelPending={false}
          currentUserRole={role}
          riskRatingsRestricted={riskRatingsRestricted}
        />,
      );

      expect(screen.getByRole("link", { name: label })).toHaveAttribute(
        "href",
        href,
      );
    },
  );

  it("keeps long batch rows and mobile actions contained", () => {
    const longBatchName =
      "Ultra-long diligence portfolio for cross-border counsel review with oncology backup compounds";
    const longBatchId =
      "batch_ultra_long_enterprise_identifier_for_q3_platform_diligence_2026_with_many_segments";
    render(
      <BatchesTable
        items={[
          {
            ...batches[1],
            id: longBatchId,
            name: longBatchName,
            status: "running",
            analysis_ids: ["analysis-long"],
          },
        ]}
        onOpenDetails={vi.fn()}
        onCancel={vi.fn()}
        cancelPending={false}
        currentUserRole="attorney"
        riskRatingsRestricted={false}
      />,
    );

    const row = screen.getByText(longBatchName).closest("tr");
    expect(row).not.toBeNull();
    expect(screen.getByText(longBatchName)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longBatchId)).toHaveClass("break-all");
    expect(screen.getByRole("table")).toHaveClass("min-[1440px]:min-w-[960px]");
    expect(
      within(row!).getByRole("link", { name: /Open report/i }),
    ).toHaveClass("min-h-11", "w-full", "sm:w-auto");
    expect(within(row!).getByRole("button", { name: /Details/i })).toHaveClass(
      "min-h-11",
      "w-full",
      "sm:w-auto",
    );
    expect(
      within(row!).getByRole("button", {
        name: /Review cancellation impact/i,
      }),
    ).toHaveClass("min-h-11", "w-full", "sm:w-auto");
  });

  it("reviews batch cancellation impact in a durable dialog before cancelling", () => {
    const onCancel = vi.fn();
    render(
      <BatchesTable
        items={batches}
        onOpenDetails={vi.fn()}
        onCancel={onCancel}
        cancelPending={false}
        currentUserRole="attorney"
        riskRatingsRestricted={false}
      />,
    );

    const runningRow = screen.getByText("Backlog triage").closest("tr");
    expect(runningRow).not.toBeNull();

    const cancelButton = within(runningRow!).getByRole("button", {
      name: /Review cancellation impact for Backlog triage/i,
    });

    fireEvent.click(cancelButton);
    const dialog = screen.getByRole("dialog", { name: "Cancel batch run?" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText("Batch under review")).toBeInTheDocument();
    expect(within(dialog).getByText("batch-2")).toBeInTheDocument();
    expect(within(dialog).getByText("Total compounds")).toBeInTheDocument();
    expect(within(dialog).getByText("Finished")).toBeInTheDocument();
    expect(within(dialog).getByText("Failures")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Total compounds").closest("div"),
    ).toHaveClass("rounded-lg");
    expect(
      within(dialog).getByRole("button", { name: "Keep running" }),
    ).toHaveClass("min-h-11");
    expect(
      within(dialog).getByRole("button", { name: "Confirm cancellation" }),
    ).toHaveClass("min-h-11");

    fireEvent.blur(cancelButton);
    expect(
      screen.getByRole("dialog", { name: "Cancel batch run?" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Keep running" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onCancel).not.toHaveBeenCalled();

    fireEvent.click(cancelButton);
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm cancellation" }),
    );
    expect(onCancel).toHaveBeenCalledWith("batch-2");
  });

  it("creates a trimmed batch and closes after mutation success", () => {
    const onClose = vi.fn();
    mockCreateMutate.mockImplementation((_payload, options) =>
      options.onSuccess(),
    );
    render(<CreateBatchForm onClose={onClose} />);

    const submit = screen.getByRole("button", { name: /Start Batch/i });
    expect(submit).toBeDisabled();
    expect(submit).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass(
      "min-h-11",
    );
    expect(
      screen.getByRole("button", { name: "Close batch form" }),
    ).toHaveClass("h-11", "w-11");
    expect(screen.getByLabelText("Batch Name")).toHaveClass("h-11");

    fireEvent.change(screen.getByLabelText("Batch Name"), {
      target: { value: "  Q2 leads  " },
    });
    fireEvent.change(screen.getByLabelText("Compounds (one per line)"), {
      target: { value: " aspirin \n\nCCO\n " },
    });

    expect(screen.getByText("2 compounds")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start Batch (2)" }));

    expect(mockCreateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Q2 leads",
        compounds: ["aspirin", "CCO"],
        client_idempotency_key: expect.stringMatching(/^batch-launch-/),
      }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("retries an unknown launch outcome with the same idempotency key", () => {
    mockCreateMutate.mockImplementation((_payload, options) => {
      options.onError();
      options.onSettled();
    });
    render(<CreateBatchForm onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Batch Name"), {
      target: { value: "Retry-safe launch" },
    });
    fireEvent.change(screen.getByLabelText("Compounds (one per line)"), {
      target: { value: "aspirin\nibuprofen" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Batch (2)" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      /Retry to reconcile this same batch without duplicate reports or charges/i,
    );
    const firstKey = mockCreateMutate.mock.calls[0][0].client_idempotency_key;

    fireEvent.click(screen.getByRole("button", { name: "Start Batch (2)" }));
    const secondKey = mockCreateMutate.mock.calls[1][0].client_idempotency_key;
    expect(secondKey).toBe(firstKey);

    fireEvent.change(screen.getByLabelText("Batch Name"), {
      target: { value: "Changed retry payload" },
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start Batch (2)" }));
    const changedPayloadKey =
      mockCreateMutate.mock.calls[2][0].client_idempotency_key;
    expect(changedPayloadKey).not.toBe(firstKey);
  });

  it("explains deterministic capacity exhaustion and routes to Report Credits", () => {
    mockCreateMutate.mockImplementation((_payload, options) => {
      options.onError(
        new APIError(429, "capacity exhausted", undefined, {
          typeUri:
            "https://problems.praviar.invalid/analysis-capacity-exhausted",
        }),
      );
      options.onSettled();
    });
    render(<CreateBatchForm onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Batch Name"), {
      target: { value: "Capacity-gated launch" },
    });
    fireEvent.change(screen.getByLabelText("Compounds (one per line)"), {
      target: { value: "aspirin\nibuprofen" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Batch (2)" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "No batch or analyses were created",
    );
    expect(
      screen.getByRole("link", { name: "Review Report Credits" }),
    ).toHaveAttribute(
      "href",
      "/billing?intent=credits&needed_reports=2&source=batch",
    );
  });

  it("locks the create batch form while submission is pending", async () => {
    const onClose = vi.fn();
    mockCreateMutate.mockImplementation(() => undefined);
    render(<CreateBatchForm onClose={onClose} />);

    fireEvent.change(screen.getByLabelText("Batch Name"), {
      target: { value: "Pending launch" },
    });
    fireEvent.change(screen.getByLabelText("Compounds (one per line)"), {
      target: { value: "aspirin\nibuprofen" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Start Batch (2)" }));

    expect(mockCreateMutate).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Batch Name")).toBeDisabled();
    expect(screen.getByLabelText("Compounds (one per line)")).toBeDisabled();
    expect(screen.getByLabelText("Close batch form")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Start Batch/i })).toBeDisabled();

    fireEvent.click(screen.getByLabelText("Close batch form"));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("matches the backend 50-compound batch limit before submission", () => {
    render(<CreateBatchForm onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Batch Name"), {
      target: { value: "Oversized batch" },
    });
    fireEvent.change(screen.getByLabelText("Compounds (one per line)"), {
      target: {
        value: Array.from(
          { length: 51 },
          (_, index) => `compound-${index + 1}`,
        ).join("\n"),
      },
    });

    expect(
      screen.getByText("Too many compounds (51/50 max)."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start Batch (51)" }),
    ).toBeDisabled();
    expect(mockCreateMutate).not.toHaveBeenCalled();
  });

  it("renders batch detail loading, empty, and linked analysis states", () => {
    const onClose = vi.fn();
    mockUseBatch.mockReturnValue({ data: undefined, isLoading: true });
    const { rerender } = render(
      <BatchDetailPanel
        batchId="batch-1"
        batchName="Launch compounds"
        onClose={onClose}
        currentUserRole="attorney"
        riskRatingsRestricted={false}
      />,
    );

    expect(screen.getByText("Launch compounds")).toBeInTheDocument();
    expect(screen.getByText("batch-1")).toBeInTheDocument();
    expect(screen.getByTestId("batch-detail-panel")).toHaveAttribute(
      "data-batch-id",
      "batch-1",
    );
    expect(
      screen.queryByText("No analyses in this batch yet"),
    ).not.toBeInTheDocument();

    mockUseBatch.mockReturnValue({
      data: { ...batches[0], analysis_ids: [] },
      isLoading: false,
    });
    rerender(
      <BatchDetailPanel
        batchId="batch-1"
        batchName="Launch compounds"
        onClose={onClose}
        currentUserRole="attorney"
        riskRatingsRestricted={false}
      />,
    );
    expect(
      screen.getByText("No analyses in this batch yet"),
    ).toBeInTheDocument();

    mockUseBatch.mockReturnValue({
      data: { ...batches[0], analysis_ids: ["analysis-abcdef123"] },
      isLoading: false,
    });
    rerender(
      <BatchDetailPanel
        batchId="batch-1"
        batchName="Launch compounds"
        onClose={onClose}
        currentUserRole="attorney"
        riskRatingsRestricted={false}
      />,
    );
    expect(screen.getByText("Batch progress")).toBeInTheDocument();
    expect(screen.getByText("Available analysis packets")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /analysis-abcde/i }),
    ).toHaveAttribute("href", "/analyses/analysis-abcdef123");
    expect(
      screen.getByRole("link", { name: /Open counsel report/i }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("link", { name: /Open counsel report/i }),
    ).toHaveAttribute(
      "href",
      "/analyses/analysis-abcdef123/report?audience=diligence&ai_context=review_questions&tab=claims",
    );

    rerender(
      <BatchDetailPanel
        batchId="batch-1"
        batchName="Launch compounds"
        onClose={onClose}
        currentUserRole="scientist"
        riskRatingsRestricted
      />,
    );
    expect(
      screen.getByRole("link", { name: "Open authorized summary" }),
    ).toHaveAttribute("href", "/analyses/analysis-abcdef123/report/summary");

    const closeButton = screen.getByRole("button", {
      name: "Close batch details",
    });
    expect(closeButton).toHaveClass("h-11", "w-11");
    fireEvent.click(closeButton);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("hides selected batch identifiers when detail access is revoked", () => {
    mockUseBatch.mockReturnValue({
      data: { ...batches[0], analysis_ids: ["analysis-private-123"] },
      error: new APIError(403, "Forbidden"),
      isLoading: false,
      isError: true,
    });

    render(
      <BatchDetailPanel
        batchId="batch-1"
        batchName="Launch compounds"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Batch details restricted")).toBeInTheDocument();
    expect(screen.getByText("Access restricted")).toBeInTheDocument();
    expect(
      screen.getByText(/Cached batch identifiers, report links, and progress/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Batch details access restricted"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Launch compounds")).not.toBeInTheDocument();
    expect(screen.queryByText("batch-1")).not.toBeInTheDocument();
    expect(screen.queryByText("analysis-priva")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open counsel report" }),
    ).not.toBeInTheDocument();
  });

  it("wires header and pagination controls without rendering unnecessary pagination", () => {
    const onToggleCreate = vi.fn();
    const onPrevious = vi.fn();
    const onNext = vi.fn();

    render(<BatchPageHeader onToggleCreate={onToggleCreate} />);
    fireEvent.click(screen.getByRole("button", { name: /New Batch/i }));
    expect(onToggleCreate).toHaveBeenCalledTimes(1);

    const { rerender } = render(
      <BatchPagination
        page={2}
        totalPages={3}
        total={24}
        onPrevious={onPrevious}
        onNext={onNext}
      />,
    );
    expect(screen.getByText("Page 2 of 3 (24 total)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPrevious).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledTimes(1);

    rerender(
      <BatchPagination
        page={1}
        totalPages={1}
        total={2}
        onPrevious={onPrevious}
        onNext={onNext}
      />,
    );
    expect(screen.queryByText(/Page 1 of 1/)).not.toBeInTheDocument();
  });
});
