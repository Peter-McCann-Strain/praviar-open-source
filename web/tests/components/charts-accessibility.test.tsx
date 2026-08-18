import type React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("recharts", () => {
  const SvgContainer = ({
    accessibilityLayer,
    children,
    variant = "bar",
  }: {
    accessibilityLayer?: boolean;
    children?: React.ReactNode;
    variant?: "bar" | "pie";
  }) => (
    <svg
      data-testid={`${variant}-chart`}
      data-accessibility-layer={String(accessibilityLayer)}
    >
      {children}
    </svg>
  );
  const NullPart = () => null;

  return {
    BarChart: (props: {
      accessibilityLayer?: boolean;
      children?: React.ReactNode;
    }) => <SvgContainer {...props} variant="bar" />,
    CartesianGrid: NullPart,
    Cell: NullPart,
    LabelList: NullPart,
    Legend: NullPart,
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => (
      <div data-testid="responsive-container">{children}</div>
    ),
    Tooltip: NullPart,
    XAxis: NullPart,
    YAxis: NullPart,
    Bar: ({
      animationBegin,
      animationDuration,
      children,
      dataKey,
      isAnimationActive,
    }: {
      animationBegin?: number;
      animationDuration?: number;
      children?: React.ReactNode;
      dataKey: string;
      isAnimationActive?: boolean;
    }) => (
      <g
        data-testid={`bar-${dataKey}`}
        data-animation-active={String(isAnimationActive)}
        data-animation-begin={String(animationBegin)}
        data-animation-duration={String(animationDuration)}
      >
        {children}
      </g>
    ),
    PieChart: (props: {
      accessibilityLayer?: boolean;
      children?: React.ReactNode;
    }) => <SvgContainer {...props} variant="pie" />,
    Pie: ({
      animationDuration,
      children,
      dataKey,
      isAnimationActive,
      rootTabIndex,
    }: {
      animationDuration?: number;
      children?: React.ReactNode;
      dataKey: string;
      isAnimationActive?: boolean;
      rootTabIndex?: number;
    }) => (
      <g
        data-testid={`pie-${dataKey}`}
        data-animation-active={String(isAnimationActive)}
        data-animation-duration={String(animationDuration)}
        tabIndex={rootTabIndex}
      >
        {children}
      </g>
    ),
  };
});

import { RiskDonut } from "@/components/charts/risk-donut";
import { SearchFunnel } from "@/components/charts/search-funnel";
import { TimingWaterfall } from "@/components/charts/timing-waterfall";
import { UsageChart } from "@/components/charts/usage-chart";

function mockReducedMotion(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      addEventListener: vi.fn(),
      addListener: vi.fn(),
      dispatchEvent: vi.fn(),
      matches,
      media: query,
      onchange: null,
      removeEventListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  });
}

describe("evidence chart accessibility", () => {
  beforeEach(() => {
    mockReducedMotion(false);
  });

  it("gives the search funnel an accessible summary without duplicate hidden lists", () => {
    render(
      <SearchFunnel
        data={[
          { stage: "Found", count: 1240 },
          { stage: "Triaged", count: 88 },
          { stage: "Analyzed", count: 12 },
        ]}
      />,
    );

    const chart = screen.getByRole("img", {
      name: "Search funnel chart",
    });

    expect(chart).toBeInTheDocument();
    expect(chart).toHaveAccessibleDescription(
      /Found 1,240 patents, Triaged 88 patents, Analyzed 12 patents\. Found: 1,240 patents; Triaged: 88 patents; Analyzed: 12 patents/,
    );
    expect(screen.getByTestId("bar-chart")).toHaveAttribute(
      "data-accessibility-layer",
      "false",
    );
    expect(chart).toHaveAccessibleDescription(/Analyzed: 12 patents/);
    expect(screen.queryByText("Analyzed: 12 patents")).not.toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("gives the timing waterfall total, slowest-step, and per-step text without duplicate hidden lists", () => {
    render(
      <TimingWaterfall
        data={[
          { step: "Resolve", duration_seconds: 0.42 },
          { step: "Search", duration_seconds: 5.4 },
          { step: "Report", duration_seconds: 61.2 },
        ]}
      />,
    );

    const chart = screen.getByRole("img", {
      name: "Timing waterfall chart",
    });

    expect(chart).toBeInTheDocument();
    expect(chart).toHaveAccessibleDescription(
      /Total runtime 1m 7s; slowest step Report at 1m 1s;.*Resolve: 420ms; Search: 5\.4s; Report: 1m 1s/,
    );
    expect(screen.getByTestId("bar-chart")).toHaveAttribute(
      "data-accessibility-layer",
      "false",
    );
    expect(chart).toHaveAccessibleDescription(/Resolve: 420ms/);
    expect(screen.queryByText("Report: 1m 1s")).not.toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("gives the usage chart token totals and per-step text", () => {
    render(
      <UsageChart
        data={[
          { step: "Search", input_tokens: 1200, output_tokens: 340 },
          { step: "Rank", input_tokens: 500, output_tokens: 100 },
        ]}
      />,
    );

    const chart = screen.getByRole("img", {
      name: "Token usage chart",
    });

    expect(chart).toBeInTheDocument();
    expect(chart).toHaveAccessibleDescription(
      /1\.7k input tokens and 440 output tokens across 2 steps;.*Search: 1\.2k input tokens, 340 output tokens; Rank: 500 input tokens, 100 output tokens/,
    );
    expect(screen.getByTestId("bar-chart")).toHaveAttribute(
      "data-accessibility-layer",
      "false",
    );
    expect(chart).toHaveAccessibleDescription(
      /Rank: 500 input tokens, 100 output tokens/,
    );
    expect(
      screen.queryByText("Rank: 500 input tokens, 100 output tokens"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("disables chart bar animation when the user prefers reduced motion", async () => {
    mockReducedMotion(true);

    render(
      <UsageChart
        data={[
          { step: "Search", input_tokens: 1200, output_tokens: 340 },
          { step: "Rank", input_tokens: 500, output_tokens: 100 },
        ]}
      />,
    );

    expect(screen.getByTestId("bar-input_tokens")).toHaveAttribute(
      "data-animation-active",
      "false",
    );
    expect(screen.getByTestId("bar-input_tokens")).toHaveAttribute(
      "data-animation-duration",
      "0",
    );
    expect(screen.getByTestId("bar-output_tokens")).toHaveAttribute(
      "data-animation-begin",
      "0",
    );
  });

  it("keeps RiskDonut on the same external chart semantics", () => {
    render(
      <RiskDonut
        data={[
          { level: "HIGH", count: 2 },
          { level: "LOW", count: 1 },
        ]}
      />,
    );

    const chart = screen.getByRole("img", {
      name: "Risk distribution chart",
    });

    expect(chart).toHaveAccessibleDescription(
      /3 patents: 2 high, 1 low\. HIGH: 2 of 3 patents; LOW: 1 of 3 patents/,
    );
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByText("HIGH: 2 of 3 patents")).not.toBeInTheDocument();
    expect(screen.getByTestId("pie-chart")).toHaveAttribute(
      "data-accessibility-layer",
      "false",
    );
    expect(chart.querySelector('[tabindex="0"]')).not.toBeInTheDocument();
    expect(screen.getAllByTestId(/^pie-/u)).toHaveLength(3);
    expect(screen.getByTestId("pie-count")).toHaveAttribute("tabindex", "-1");
    expect(screen.getByTestId("pie-value")).toHaveAttribute("tabindex", "-1");
  });

  it("shows a visible RiskDonut legend without duplicating screen-reader chart text", () => {
    render(
      <RiskDonut
        data={[
          { level: "HIGH", count: 2 },
          { level: "LOW", count: 1 },
        ]}
      />,
    );

    const legend = screen.getByTestId("risk-donut-legend");

    expect(legend).toHaveAttribute("aria-hidden", "true");
    expect(legend).toHaveClass("min-[420px]:grid-cols-2");
    expect(legend).not.toHaveClass("xl:grid-cols-4");
    expect(screen.getByText("High")).toBeVisible();
    expect(screen.getByText("Low")).toBeVisible();
    expect(screen.getByText("67%")).toBeVisible();
    expect(screen.getByText("33%")).toBeVisible();
    expect(legend.querySelectorAll(".praviar-chart-swatch")).toHaveLength(2);
  });

  it("renders nonblank empty states for charts with no data", () => {
    render(
      <>
        <SearchFunnel data={[]} height={180} />
        <TimingWaterfall data={[]} height={180} />
        <UsageChart data={[]} height={180} />
      </>,
    );

    expect(
      screen.getByRole("img", {
        name: "Search funnel chart",
      }),
    ).toHaveTextContent("No funnel data");
    expect(
      screen.getByRole("img", {
        name: "Timing waterfall chart",
      }),
    ).toHaveTextContent("No timing data");
    expect(
      screen.getByRole("img", {
        name: "Token usage chart",
      }),
    ).toHaveTextContent("No token usage");
  });
});
