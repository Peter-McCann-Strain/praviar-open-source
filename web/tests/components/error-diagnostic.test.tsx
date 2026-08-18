import { StrictMode } from "react";
import { render } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";

function DiagnosticProbe({
  active,
  error,
  report,
}: {
  active: boolean;
  error: unknown;
  report: (currentError: unknown) => void;
}) {
  useErrorDiagnostic(active, error, report);
  return <div>Diagnostic probe</div>;
}

describe("useErrorDiagnostic", () => {
  it("reports one diagnostic per distinct error under StrictMode", () => {
    const report = vi.fn();
    const firstError = new Error("first failure");
    const secondError = new Error("second failure");
    const { rerender } = render(
      <StrictMode>
        <DiagnosticProbe active error={firstError} report={report} />
      </StrictMode>,
    );

    expect(report).toHaveBeenCalledTimes(1);
    expect(report).toHaveBeenLastCalledWith(firstError);

    rerender(
      <StrictMode>
        <DiagnosticProbe active error={firstError} report={report} />
      </StrictMode>,
    );
    expect(report).toHaveBeenCalledTimes(1);

    rerender(
      <StrictMode>
        <DiagnosticProbe active error={secondError} report={report} />
      </StrictMode>,
    );
    expect(report).toHaveBeenCalledTimes(2);
    expect(report).toHaveBeenLastCalledWith(secondError);
  });

  it("resets after recovery so a later retry failure can report again", () => {
    const report = vi.fn();
    const retryError = new Error("retry failure");
    const { rerender } = render(
      <DiagnosticProbe active error={retryError} report={report} />,
    );

    rerender(<DiagnosticProbe active={false} error={null} report={report} />);
    rerender(<DiagnosticProbe active error={retryError} report={report} />);

    expect(report).toHaveBeenCalledTimes(2);
  });

  it("does not report during render", () => {
    const report = vi.fn();

    renderToString(
      <DiagnosticProbe
        active
        error={new Error("server render failure")}
        report={report}
      />,
    );

    expect(report).not.toHaveBeenCalled();
  });
});
