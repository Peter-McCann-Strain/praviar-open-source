import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReportStatusState } from "@/components/report-page/report-status-state";

describe("ReportStatusState", () => {
  it("renders auth resolution without implying a missing report", () => {
    render(<ReportStatusState variant="auth" />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Checking report access",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No report content exposed")).toBeInTheDocument();
    expect(screen.queryByText("Report not available")).not.toBeInTheDocument();
  });

  it("renders a governed loading state without exposing report actions", () => {
    const { container } = render(<ReportStatusState variant="loading" />);

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Loading report workspace",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No report content shown yet")).toBeInTheDocument();
    expect(screen.getByText("Actions open after load")).toBeInTheDocument();
    expect(container.querySelector("svg.animate-spin")).toHaveClass(
      "motion-reduce:animate-none",
    );
  });

  it("renders package-readiness failures as blocked report states with bounded detail", () => {
    render(
      <ReportStatusState
        variant="validation"
        analysisId="ana-1"
        analysisStatus="completed"
        analysisUpdatedAt="2026-06-19T10:42:00Z"
        currentStep={8}
        totalPatentsFound={2417}
        detail={`compound.name: Required postgres://secret-host/praviar ${"sk" + "_live_" + "1234567890abcdef"} ${"schema drift ".repeat(24)}`}
      />,
    );

    expect(screen.getByRole("alert")).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Report package could not be verified",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Report rendering blocked")).toBeInTheDocument();
    expect(screen.getByText("Existing data unchanged")).toBeInTheDocument();
    expect(screen.getByText("Support review required")).toBeInTheDocument();
    expect(screen.getByText("No legal conclusion changed")).toBeInTheDocument();
    expect(screen.getByText("Evidence preserved")).toBeInTheDocument();
    expect(screen.getByText("2,417 patents found")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toHaveTextContent("schema-invalid report content hidden");
    expect(
      screen.getByRole("link", { name: /Open analysis status/i }),
    ).toHaveAttribute("href", "/analyses/ana-1");
    fireEvent.click(screen.getByText("View support reference"));
    expect(
      screen.getByText("Support reference", { selector: "p" }),
    ).toBeInTheDocument();
    const reference = screen.getByText(/^Report validation reference/u);
    expect(reference.textContent).toMatch(
      /^Report validation reference [A-Z0-9]+$/u,
    );
    expect(reference.textContent).not.toContain("compound.name");
    expect(reference.textContent).not.toContain("schema drift");
    expect(
      screen.queryByText(/postgres:\/\/secret-host/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/sk_live_1234567890abcdef/i),
    ).not.toBeInTheDocument();
  });

  it("keeps blocked access copy private and team-scoped", () => {
    render(<ReportStatusState variant="forbidden" />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Report access unavailable",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Team-scoped access")).toBeInTheDocument();
    expect(screen.getByText("No report content exposed")).toBeInTheDocument();
    expect(
      screen.getByText(/does not confirm whether report artifacts/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Evidence preserved")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/preserved report inputs/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/reviewer records unchanged/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/patent/i)).not.toBeInTheDocument();
  });

  it("offers a retry action for temporary failures", () => {
    const onRetry = vi.fn();
    render(
      <ReportStatusState
        variant="temporary"
        analysisId="ana-2"
        analysisStatus="completed"
        currentStep={8}
        onRetry={onRetry}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry report load" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Report temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No report edits made")).toBeInTheDocument();
    expect(screen.getByText("No legal conclusion changed")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toHaveTextContent("fresh report response");
  });

  it("renders missing reports without implying a legal or FTO conclusion", () => {
    render(<ReportStatusState variant="missing" />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Report not available" }),
    ).toBeInTheDocument();
    expect(screen.getByText("No report content loaded")).toBeInTheDocument();
    expect(screen.getByText("Workspace actions disabled")).toBeInTheDocument();
    expect(
      screen.queryByText(/Retry requests a fresh report response/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/clearance/i)).not.toBeInTheDocument();
  });

  it("distinguishes reports still being prepared from missing artifacts", () => {
    render(
      <ReportStatusState
        variant="missing"
        analysisId="ana-running"
        analysisStatus="running"
        currentStep={4}
      />,
    );

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Report is still being prepared",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Report preparation in progress"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Confirm report generation"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Step 4 of 8")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Open analysis status/i }),
    ).toHaveAttribute("href", "/analyses/ana-running");
  });

  it("guides failed analyses back to analysis status before rerun", () => {
    render(
      <ReportStatusState
        variant="missing"
        analysisId="ana-failed"
        analysisStatus="failed"
        currentStep={5}
        totalPatentsFound={183}
      />,
    );

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Report was not produced",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No legal conclusion changed")).toBeInTheDocument();
    expect(screen.getByText("183 patents found")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toHaveTextContent("last completed pipeline step");
  });
});
