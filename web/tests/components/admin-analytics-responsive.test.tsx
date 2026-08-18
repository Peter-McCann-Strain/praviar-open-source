import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AuditLogTab } from "@/components/admin-analytics/audit-log-tab";
import { CostsTab } from "@/components/admin-analytics/costs-tab";
import {
  buildModelDonutData,
  buildCostAnalyticsCsv,
  formatPercentLike,
} from "@/components/admin-analytics/helpers";
import { ModelsTab } from "@/components/admin-analytics/models-tab";
import { UsageTab } from "@/components/admin-analytics/usage-tab";
import type {
  AuditLogListResponse,
  CostBreakdownResponse,
  ModelUsageResponse,
  UsageAnalyticsResponse,
} from "@/hooks/use-admin-analytics";

vi.mock("recharts", () => ({
  Bar: ({
    children,
    isAnimationActive,
  }: {
    children?: React.ReactNode;
    isAnimationActive?: boolean;
  }) => <g data-bar-animation-active={String(isAnimationActive)}>{children}</g>,
  BarChart: ({
    accessibilityLayer,
    children,
  }: {
    accessibilityLayer?: boolean;
    children?: React.ReactNode;
  }) => (
    <svg
      data-testid="bar-chart"
      data-accessibility-layer={String(accessibilityLayer)}
    >
      {children}
    </svg>
  ),
  CartesianGrid: () => <g data-testid="cartesian-grid" />,
  Cell: () => <rect data-testid="cell" />,
  Line: ({ isAnimationActive }: { isAnimationActive?: boolean }) => (
    <path data-line-animation-active={String(isAnimationActive)} />
  ),
  LineChart: ({
    accessibilityLayer,
    children,
  }: {
    accessibilityLayer?: boolean;
    children?: React.ReactNode;
  }) => (
    <svg
      data-testid="line-chart"
      data-accessibility-layer={String(accessibilityLayer)}
    >
      {children}
    </svg>
  ),
  Pie: ({
    children,
    isAnimationActive,
  }: {
    children?: React.ReactNode;
    isAnimationActive?: boolean;
  }) => <g data-animation-active={String(isAnimationActive)}>{children}</g>,
  PieChart: ({
    children,
    accessibilityLayer,
  }: {
    children?: React.ReactNode;
    accessibilityLayer?: boolean;
  }) => (
    <svg
      data-testid="pie-chart"
      data-accessibility-layer={String(accessibilityLayer)}
    >
      {children}
    </svg>
  ),
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  Tooltip: () => <g data-testid="tooltip" />,
  XAxis: () => <g data-testid="x-axis" />,
  YAxis: () => <g data-testid="y-axis" />,
}));

describe("admin analytics responsive surfaces", () => {
  const auditData: AuditLogListResponse = {
    items: [
      {
        id: "audit-1",
        org_id: "org-1",
        action: "report.shared",
        user_id: "user-1",
        user_email: "admin@acme.example",
        analysis_id: "analysis-1",
        details: {
          compound_name: "succinic acid",
          api_key: "secret-key-should-not-render",
          message:
            "postgres://secret-host/praviar sk_live_secret sk-proj-prodsecretjwt SELECT * FROM audit_log UPDATE users SET role='admin' Traceback provider stack",
          request: {
            note: "Bearer abc123 /Users/example-user/private/export.json password=hunter2 eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature",
          },
        },
        ip_address: "203.0.113.12",
        created_at: "2026-06-12T09:30:00Z",
      },
    ],
    total: 75,
    page: 1,
    per_page: 50,
    has_next: true,
  };

  const modelData: ModelUsageResponse = {
    models: [
      {
        model_name: "anthropic/claude-sonnet-4-6",
        total_input_tokens: 480_000,
        total_output_tokens: 72_000,
        total_tokens: 552_000,
        estimated_cost_usd: 5.52,
        request_count: 22,
        cache_hit_rate: 41,
      },
    ],
    total_tokens: 552_000,
    total_cost_usd: 5.52,
    overall_cache_hit_rate: 41,
    period: "month",
  };

  const usageData: UsageAnalyticsResponse = {
    org_usage: [
      {
        org_id: "org-1",
        org_name: "Acme Therapeutics With A Long Name",
        analysis_count: 18,
        total_cost_usd: 8.48,
        avg_cost_usd: 0.471,
      },
    ],
    status_breakdown: [{ status: "completed", count: 16 }],
    top_compounds: [
      {
        compound_name:
          "N-(4-hydroxyphenyl)-2-(4-isobutylphenyl)propanamide analog",
        compound_smiles: "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        analysis_count: 4,
      },
    ],
    total_analyses: 18,
    avg_cost_per_analysis: 0.471,
    avg_duration_seconds: 612,
    period: "month",
  };

  const costData: CostBreakdownResponse = {
    daily_costs: [
      {
        date: "2026-06-01",
        total_cost_usd: 12.5,
        analysis_count: 3,
        total_input_tokens: 100_000,
        total_output_tokens: 8_000,
      },
    ],
    step_costs: [
      {
        step_name: "claim charting",
        total_cost_usd: 8.25,
        analysis_count: 2,
        avg_cost_usd: 4.125,
      },
    ],
    model_costs: [],
    total_cost_usd: 12.5,
    total_input_tokens: 100_000,
    total_output_tokens: 8_000,
    period: "month",
    start_date: "2026-06-01",
    end_date: "2026-06-30",
  };

  it("renders audit log rows with mobile-readable labels and pagination", () => {
    const onPreviousPage = vi.fn();
    const onNextPage = vi.fn();

    render(
      <AuditLogTab
        auditData={auditData}
        auditLoading={false}
        auditFilters={{}}
        auditPage={1}
        onFiltersChange={vi.fn()}
        onPreviousPage={onPreviousPage}
        onNextPage={onNextPage}
        onResetPage={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(
      screen.getByText(/entries total\. Filters apply/i),
    ).toHaveTextContent("75 entries total");
    expect(
      screen.getByRole("region", { name: "Audit log filters" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Export current page CSV" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("region", { name: "Admin analytics audit log" }),
    ).toHaveAttribute("tabIndex", "0");
    expect(
      screen.getByText(/Admin analytics audit log with timestamp/i),
    ).toBeInTheDocument();
    for (const header of screen.getAllByRole("columnheader")) {
      expect(header).toHaveAttribute("scope", "col");
    }
    expect(screen.getByText("report.shared")).toBeInTheDocument();
    expect(screen.getByText("admin@acme.example")).toBeInTheDocument();
    expect(screen.getByText("203.0.113.12")).toBeInTheDocument();
    expect(screen.getByText("Compound reference recorded")).toBeInTheDocument();
    expect(screen.queryByText(/succinic acid/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/secret-key-should-not-render/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/postgres:\/\/secret-host/i),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Inspect details" }));
    expect(
      screen.getByRole("complementary", { name: "Audit event detail" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Safe raw metadata")).toBeInTheDocument();
    expect(
      screen.getByText(/"compound_name": "succinic acid"/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/"api_key": "\[redacted\]"/i)).toBeInTheDocument();
    expect(
      screen.getByText(/\[redacted connection string\]/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/\[redacted API key\]/i)).toBeInTheDocument();
    expect(screen.getByText(/\[redacted token\]/i)).toBeInTheDocument();
    expect(screen.getByText(/Bearer \[redacted\]/i)).toBeInTheDocument();
    expect(screen.getByText(/\[redacted path\]/i)).toBeInTheDocument();
    expect(screen.getByText(/password=\[redacted\]/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/secret-key-should-not-render/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/postgres:\/\/secret-host/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/sk_live_secret/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/sk-proj-prodsecretjwt/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/SELECT \* FROM audit_log/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/UPDATE users/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Bearer abc123/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hunter2/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/eyJhbGciOiJIUzI1NiJ9/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/\/Users\/peter\/private/i),
    ).not.toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Previous" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Next" })).toHaveClass(
      "min-h-11",
    );

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onNextPage).toHaveBeenCalledTimes(1);
    expect(onPreviousPage).not.toHaveBeenCalled();
  });

  it("renders cost charts with accessible summaries and reduced-motion animation", () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });

    const { container } = render(
      <CostsTab costData={costData} costLoading={false} onRetry={vi.fn()} />,
    );

    expect(
      screen.getByRole("img", { name: "Cost over time chart" }),
    ).toHaveAccessibleDescription(/2026-06-01: \$12.50 across 3 analyses/i);
    expect(
      screen.getByRole("img", { name: "Cost by pipeline step chart" }),
    ).toHaveAccessibleDescription(/claim charting: \$8.25 across 2 analyses/i);
    expect(screen.getByTestId("line-chart")).toHaveAttribute(
      "data-accessibility-layer",
      "true",
    );
    expect(screen.getByTestId("bar-chart")).toHaveAttribute(
      "data-accessibility-layer",
      "true",
    );
    expect(
      container.querySelector("[data-line-animation-active='false']"),
    ).toBeTruthy();
    expect(
      container.querySelector("[data-bar-animation-active='false']"),
    ).toBeTruthy();
    window.matchMedia = originalMatchMedia;
  });

  it("renders explicit empty states instead of blank cost chart frames", () => {
    render(
      <CostsTab
        costData={{ ...costData, daily_costs: [], step_costs: [] }}
        costLoading={false}
        onRetry={vi.fn()}
      />,
    );

    expect(
      screen.getByText("No daily spend in this period"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No pipeline step spend in this period"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("line-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("bar-chart")).not.toBeInTheDocument();
  });

  it("renders model detail metrics in a labelled scroll region", () => {
    const modelDonutData = buildModelDonutData(modelData);
    const { container } = render(
      <ModelsTab
        modelData={modelData}
        modelLoading={false}
        modelDonutData={modelDonutData}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("Model Details")).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: "Admin analytics model detail table",
      }),
    ).toHaveAttribute("tabIndex", "0");
    expect(
      screen.getByText(/Admin analytics model detail table with model name/i),
    ).toBeInTheDocument();
    for (const header of screen.getAllByRole("columnheader")) {
      expect(header).toHaveAttribute("scope", "col");
    }
    expect(
      screen.getByRole("img", { name: "Token usage by model chart" }),
    ).toHaveAccessibleDescription(/anthropic\/claude-sonnet-4-6/i);
    expect(screen.getByText("anthropic/claude-sonnet-4-6")).toBeInTheDocument();
    expect(screen.getByText("480.0k")).toBeInTheDocument();
    expect(screen.getByText("72.0k")).toBeInTheDocument();
    expect(screen.getByText("$5.52")).toBeInTheDocument();
    expect(screen.getByText("Prompt Cache Hit Rate")).toBeInTheDocument();
    expect(screen.getByText("41%")).toBeInTheDocument();
    expect(container.querySelector(".praviar-chart-swatch")).toBeTruthy();
  });

  it("keeps provider-qualified model labels stable when display names collide", () => {
    const duplicateProviderData: ModelUsageResponse = {
      ...modelData,
      models: [
        {
          ...modelData.models[0],
          model_name: "openai/gpt-4.1",
          total_tokens: 400_000,
          estimated_cost_usd: 4,
        },
        {
          ...modelData.models[0],
          model_name: "azure/gpt-4.1",
          total_tokens: 300_000,
          estimated_cost_usd: 3,
        },
      ],
    };
    const donutData = buildModelDonutData(duplicateProviderData);

    expect(donutData.map((entry) => entry.name)).toEqual([
      "openai/gpt-4.1",
      "azure/gpt-4.1",
    ]);
    expect(donutData.map((entry) => entry.id)).toEqual([
      "openai/gpt-4.1-0",
      "azure/gpt-4.1-1",
    ]);

    render(
      <ModelsTab
        modelData={duplicateProviderData}
        modelLoading={false}
        modelDonutData={donutData}
        onRetry={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("img", { name: "Token usage by model chart" }),
    ).toHaveAccessibleDescription(/openai\/gpt-4\.1/i);
    expect(
      screen.getByRole("img", { name: "Token usage by model chart" }),
    ).toHaveAccessibleDescription(/azure\/gpt-4\.1/i);
    expect(
      screen.getByLabelText("openai/gpt-4.1: 400.0k tokens"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("azure/gpt-4.1: 300.0k tokens"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("openai/gpt-4.1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("azure/gpt-4.1").length).toBeGreaterThan(0);
  });

  it("disables model chart animation when reduced motion is preferred", () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });

    const { container } = render(
      <ModelsTab
        modelData={modelData}
        modelLoading={false}
        modelDonutData={buildModelDonutData(modelData)}
        onRetry={vi.fn()}
      />,
    );

    expect(
      container.querySelector("[data-animation-active='false']"),
    ).toBeTruthy();
    expect(screen.getByTestId("pie-chart")).toHaveAttribute(
      "data-accessibility-layer",
      "false",
    );
    window.matchMedia = originalMatchMedia;
  });

  it("lets dense usage lists wrap on mobile instead of squeezing", () => {
    render(
      <UsageTab usageData={usageData} usageLoading={false} onRetry={vi.fn()} />,
    );

    expect(
      screen.getByText("Acme Therapeutics With A Long Name"),
    ).toBeInTheDocument();
    expect(screen.getByText("18 analyses")).toBeInTheDocument();
    expect(
      screen.getByText(
        "N-(4-hydroxyphenyl)-2-(4-isobutylphenyl)propanamide analog",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("10.2m")).toBeInTheDocument();
  });

  it("renders paged-empty audit recovery instead of a false filter empty", () => {
    const onResetPage = vi.fn();

    render(
      <AuditLogTab
        auditData={{
          ...auditData,
          items: [],
          page: 3,
          total: 75,
          has_next: false,
        }}
        auditLoading={false}
        auditFilters={{}}
        auditPage={3}
        onFiltersChange={vi.fn()}
        onPreviousPage={vi.fn()}
        onNextPage={vi.fn()}
        onResetPage={onResetPage}
        onRetry={vi.fn()}
      />,
    );

    expect(
      screen.getByText("No audit events on this page"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/No audit log entries for the selected filters/i),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Return to first page" }),
    );
    expect(onResetPage).toHaveBeenCalledTimes(1);
  });

  it("formats cache percentages from the backend percent contract and exports cost CSV metadata", () => {
    expect(formatPercentLike(0.5)).toBe("0.5%");
    expect(formatPercentLike(1)).toBe("1%");
    expect(formatPercentLike(41)).toBe("41%");
    expect(formatPercentLike(null)).toBe("N/A");

    const csv = buildCostAnalyticsCsv(
      [
        {
          date: "2026-06-12",
          total_cost_usd: 1.2345,
          analysis_count: 2,
          total_input_tokens: 100,
          total_output_tokens: 25,
        },
      ],
      { period: "month, with comma", generatedAt: "2026-06-17T21:00:00Z" },
    );

    expect(csv).toContain("Schema,Praviar analytics costs v1");
    expect(csv).toContain('Period,"month, with comma"');
    expect(csv).toContain("Generated At,2026-06-17T21:00:00Z");
    expect(csv).toContain("2026-06-12,1.2345,2,100,25");
  });
});
