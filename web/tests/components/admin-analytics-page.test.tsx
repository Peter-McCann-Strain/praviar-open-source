import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { APIError } from "@/lib/api-client";

const mockUseCostAnalytics = vi.fn();
const mockUseUsageAnalytics = vi.fn();
const mockUseModelUsage = vi.fn();
const mockUseAuditLog = vi.fn();

vi.mock("@/hooks/use-admin-analytics", () => ({
  useCostAnalytics: (...args: unknown[]) => mockUseCostAnalytics(...args),
  useUsageAnalytics: (...args: unknown[]) => mockUseUsageAnalytics(...args),
  useModelUsage: (...args: unknown[]) => mockUseModelUsage(...args),
  useAuditLog: (...args: unknown[]) => mockUseAuditLog(...args),
}));

vi.mock("recharts", () => ({
  Bar: ({ children }: { children?: React.ReactNode }) => <g>{children}</g>,
  BarChart: ({ children }: { children?: React.ReactNode }) => (
    <svg data-testid="bar-chart">{children}</svg>
  ),
  CartesianGrid: () => <g data-testid="cartesian-grid" />,
  Cell: () => <rect data-testid="cell" />,
  Line: () => <path data-testid="line" />,
  LineChart: ({ children }: { children?: React.ReactNode }) => (
    <svg data-testid="line-chart">{children}</svg>
  ),
  Pie: ({ children }: { children?: React.ReactNode }) => <g>{children}</g>,
  PieChart: ({ children }: { children?: React.ReactNode }) => (
    <svg data-testid="pie-chart">{children}</svg>
  ),
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  Tooltip: () => <g data-testid="tooltip" />,
  XAxis: () => <g data-testid="x-axis" />,
  YAxis: () => <g data-testid="y-axis" />,
}));

import AnalyticsPage from "@/app/(dashboard)/admin/analytics/page";

describe("AnalyticsPage", () => {
  const refetchCost = vi.fn();
  const refetchUsage = vi.fn();
  const refetchModels = vi.fn();
  const refetchAudit = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    refetchCost.mockResolvedValue({});
    refetchUsage.mockResolvedValue({});
    refetchModels.mockResolvedValue({});
    refetchAudit.mockResolvedValue({});
    mockUseCostAnalytics.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: refetchCost,
    });
    mockUseUsageAnalytics.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: refetchUsage,
    });
    mockUseModelUsage.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: refetchModels,
    });
    mockUseAuditLog.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: refetchAudit,
    });
  });

  it("does not render false-zero analytics while access is unavailable", () => {
    render(<AnalyticsPage />);

    const status = screen.getByRole("status", {
      name: "Checking analytics access",
    });
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Checking analytics access",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Checking analytics access")).toBeInTheDocument();
    expect(screen.queryByText("LLM Spend")).not.toBeInTheDocument();
    expect(screen.queryByText("$0.0000")).not.toBeInTheDocument();
  });

  it("renders a retryable safe state for initial analytics failures", () => {
    mockUseCostAnalytics.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("postgres://secret cost failure"),
      refetch: refetchCost,
    });

    render(<AnalyticsPage />);

    const alert = screen.getByRole("alert", {
      name: "Analytics temporarily unavailable",
    });
    expect(alert).not.toHaveAttribute("aria-busy");
    expect(alert).toHaveAttribute("aria-atomic", "true");
    expect(alert.querySelector(".text-error")).toBeTruthy();
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Analytics temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Analytics temporarily unavailable"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry analytics load" }),
    );
    expect(refetchCost).toHaveBeenCalledTimes(1);
    expect(refetchUsage).toHaveBeenCalledTimes(1);
    expect(refetchModels).toHaveBeenCalledTimes(1);
    expect(refetchAudit).toHaveBeenCalledTimes(1);
  });

  it("keeps analytics range and tab controls on the admin target-size contract", () => {
    mockUseCostAnalytics.mockReturnValue({
      data: {
        daily_costs: [],
        step_costs: [],
        model_costs: [],
        total_cost_usd: 0,
        total_input_tokens: 0,
        total_output_tokens: 0,
        period: "month",
        start_date: null,
        end_date: null,
      },
      isLoading: false,
      error: null,
      refetch: refetchCost,
    });
    mockUseUsageAnalytics.mockReturnValue({
      data: {
        org_usage: [],
        status_breakdown: [],
        top_compounds: [],
        total_analyses: 0,
        avg_cost_per_analysis: 0,
        avg_duration_seconds: 0,
        period: "month",
      },
      isLoading: false,
      error: null,
      refetch: refetchUsage,
    });
    mockUseModelUsage.mockReturnValue({
      data: {
        models: [],
        total_tokens: 0,
        total_cost_usd: 0,
        overall_cache_hit_rate: 0,
        period: "month",
      },
      isLoading: false,
      error: null,
      refetch: refetchModels,
    });
    mockUseAuditLog.mockReturnValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        per_page: 50,
        has_next: false,
      },
      isLoading: false,
      error: null,
      refetch: refetchAudit,
    });

    render(<AnalyticsPage />);

    expect(screen.getByRole("button", { name: "30 days" })).toHaveClass(
      "min-h-11",
      "focus-visible:ring-2",
    );
    expect(screen.getByRole("tab", { name: "Costs" })).toHaveClass(
      "min-h-11",
      "w-full",
      "shrink-0",
    );
    expect(
      screen.getByRole("tablist", { name: "Analytics sections" }),
    ).toHaveClass("grid", "grid-cols-2", "overflow-visible");
  });

  it("passes audit filters to the analytics audit query", async () => {
    mockUseCostAnalytics.mockReturnValue({
      data: {
        daily_costs: [],
        step_costs: [],
        model_costs: [],
        total_cost_usd: 0,
        total_input_tokens: 0,
        total_output_tokens: 0,
        period: "month",
        start_date: null,
        end_date: null,
      },
      isLoading: false,
      error: null,
      refetch: refetchCost,
    });
    mockUseUsageAnalytics.mockReturnValue({
      data: {
        org_usage: [],
        status_breakdown: [],
        top_compounds: [],
        total_analyses: 0,
        avg_cost_per_analysis: 0,
        avg_duration_seconds: 0,
        period: "month",
      },
      isLoading: false,
      error: null,
      refetch: refetchUsage,
    });
    mockUseModelUsage.mockReturnValue({
      data: {
        models: [],
        total_tokens: 0,
        total_cost_usd: 0,
        overall_cache_hit_rate: 0,
        period: "month",
      },
      isLoading: false,
      error: null,
      refetch: refetchModels,
    });
    mockUseAuditLog.mockReturnValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        per_page: 50,
        has_next: false,
      },
      isLoading: false,
      error: null,
      refetch: refetchAudit,
    });

    render(<AnalyticsPage />);

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Audit Log" }));
    fireEvent.change(await screen.findByLabelText("Audit action filter"), {
      target: { value: "report.export.queued" },
    });

    await waitFor(() => {
      expect(mockUseAuditLog).toHaveBeenLastCalledWith(1, {
        action: "report.export.queued",
      });
    });
  });

  it("keeps stale analytics visible when a refresh fails", () => {
    mockUseCostAnalytics.mockReturnValue({
      data: {
        daily_costs: [
          {
            date: "2026-06-12",
            total_cost_usd: 2.5,
            analysis_count: 3,
            total_input_tokens: 1200,
            total_output_tokens: 300,
          },
        ],
        step_costs: [],
        model_costs: [],
        total_cost_usd: 2.5,
        total_input_tokens: 1200,
        total_output_tokens: 300,
        period: "month",
        start_date: null,
        end_date: null,
      },
      isLoading: false,
      error: new Error("postgres://secret refresh failure"),
      refetch: refetchCost,
    });
    mockUseUsageAnalytics.mockReturnValue({
      data: {
        org_usage: [],
        status_breakdown: [],
        top_compounds: [],
        total_analyses: 3,
        avg_cost_per_analysis: 0.833,
        avg_duration_seconds: 72,
        period: "month",
      },
      isLoading: false,
      error: null,
      refetch: refetchUsage,
    });
    mockUseModelUsage.mockReturnValue({
      data: {
        models: [],
        total_tokens: 1500,
        total_cost_usd: 2.5,
        overall_cache_hit_rate: 0.5,
        period: "month",
      },
      isLoading: false,
      error: null,
      refetch: refetchModels,
    });
    mockUseAuditLog.mockReturnValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        per_page: 50,
        has_next: false,
      },
      isLoading: false,
      error: null,
      refetch: refetchAudit,
    });

    render(<AnalyticsPage />);

    expect(screen.getByText(/Analytics refresh failed/i)).toBeInTheDocument();
    expect(screen.getByText("LLM Spend")).toBeInTheDocument();
    expect(screen.getAllByText("$2.50").length).toBeGreaterThan(0);
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();
  });

  it("hides cached analytics immediately when an auth error arrives during another load", () => {
    mockUseCostAnalytics.mockReturnValue({
      data: {
        daily_costs: [
          {
            date: "2026-06-12",
            total_cost_usd: 2.5,
            analysis_count: 3,
            total_input_tokens: 1200,
            total_output_tokens: 300,
          },
        ],
        step_costs: [],
        model_costs: [],
        total_cost_usd: 2.5,
        total_input_tokens: 1200,
        total_output_tokens: 300,
        period: "month",
        start_date: null,
        end_date: null,
      },
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch: refetchCost,
    });
    mockUseUsageAnalytics.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: refetchUsage,
    });
    mockUseModelUsage.mockReturnValue({
      data: {
        models: [],
        total_tokens: 1500,
        total_cost_usd: 2.5,
        overall_cache_hit_rate: 0.5,
        period: "month",
      },
      isLoading: false,
      error: null,
      refetch: refetchModels,
    });
    mockUseAuditLog.mockReturnValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        per_page: 50,
        has_next: false,
      },
      isLoading: false,
      error: null,
      refetch: refetchAudit,
    });

    render(<AnalyticsPage />);

    expect(
      screen.getByRole("alert", { name: "Analytics access restricted" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("LLM Spend")).not.toBeInTheDocument();
    expect(screen.queryByText("$2.50")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tablist", { name: "Analytics sections" }),
    ).not.toBeInTheDocument();
  });

  it("hides cached analytics when admin access is revoked", () => {
    mockUseCostAnalytics.mockReturnValue({
      data: {
        daily_costs: [
          {
            date: "2026-06-12",
            total_cost_usd: 2.5,
            analysis_count: 3,
            total_input_tokens: 1200,
            total_output_tokens: 300,
          },
        ],
        step_costs: [],
        model_costs: [],
        total_cost_usd: 2.5,
        total_input_tokens: 1200,
        total_output_tokens: 300,
        period: "month",
        start_date: null,
        end_date: null,
      },
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch: refetchCost,
    });
    mockUseUsageAnalytics.mockReturnValue({
      data: {
        org_usage: [],
        status_breakdown: [],
        top_compounds: [],
        total_analyses: 3,
        avg_cost_per_analysis: 0.833,
        avg_duration_seconds: 72,
        period: "month",
      },
      isLoading: false,
      error: null,
      refetch: refetchUsage,
    });
    mockUseModelUsage.mockReturnValue({
      data: {
        models: [],
        total_tokens: 1500,
        total_cost_usd: 2.5,
        overall_cache_hit_rate: 0.5,
        period: "month",
      },
      isLoading: false,
      error: null,
      refetch: refetchModels,
    });
    mockUseAuditLog.mockReturnValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        per_page: 50,
        has_next: false,
      },
      isLoading: false,
      error: null,
      refetch: refetchAudit,
    });

    render(<AnalyticsPage />);

    expect(
      screen.getByRole("alert", { name: "Analytics access restricted" }),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("admin-analytics-status-restricted"),
    ).toBeInTheDocument();
    expect(screen.queryByText("LLM Spend")).not.toBeInTheDocument();
    expect(screen.queryByText("$2.50")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tablist", { name: "Analytics sections" }),
    ).not.toBeInTheDocument();
  });
});
