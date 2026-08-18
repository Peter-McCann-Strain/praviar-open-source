import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Input } from "@/components/ui/input";

describe("Input error state", () => {
  it("renders without error state by default", () => {
    const { container } = render(<Input placeholder="Enter value" />);
    const input = container.querySelector("input");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input?.className).not.toContain("border-red");
  });

  it("shows error border when error=true", () => {
    const { container } = render(<Input error placeholder="Enter value" />);
    const input = container.querySelector("input");
    expect(input?.className).toContain("border-error");
  });

  it("sets aria-invalid when error=true", () => {
    const { container } = render(<Input error placeholder="Enter value" />);
    const input = container.querySelector("input");
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("renders error message with role=alert", () => {
    render(
      <Input
        error
        errorMessage="This field is required"
        errorId="test-error"
        placeholder="Enter value"
      />,
    );
    const errorMsg = screen.getByRole("alert");
    expect(errorMsg).toHaveTextContent("This field is required");
  });

  it("links input to error message via aria-describedby", () => {
    const { container } = render(
      <Input
        error
        errorMessage="Invalid input"
        errorId="field-error"
        placeholder="Enter value"
      />,
    );
    const input = container.querySelector("input");
    expect(input).toHaveAttribute("aria-describedby", "field-error");
  });

  it("does not render error message when error=false", () => {
    render(
      <Input
        errorMessage="Should not appear"
        errorId="hidden-error"
        placeholder="Enter value"
      />,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
