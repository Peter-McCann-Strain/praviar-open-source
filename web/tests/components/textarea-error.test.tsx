import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Textarea } from "@/components/ui/textarea";

describe("Textarea error state", () => {
  it("renders without error state by default", () => {
    const { container } = render(<Textarea placeholder="Enter text" />);
    const textarea = container.querySelector("textarea");
    expect(textarea).not.toHaveAttribute("aria-invalid");
    expect(textarea?.className).not.toContain("border-red");
  });

  it("shows error border when error=true", () => {
    const { container } = render(<Textarea error placeholder="Enter text" />);
    const textarea = container.querySelector("textarea");
    expect(textarea?.className).toContain("border-error");
  });

  it("sets aria-invalid when error=true", () => {
    const { container } = render(<Textarea error placeholder="Enter text" />);
    const textarea = container.querySelector("textarea");
    expect(textarea).toHaveAttribute("aria-invalid", "true");
  });

  it("renders error message with role=alert", () => {
    render(
      <Textarea
        error
        errorMessage="This field is required"
        errorId="test-error"
        placeholder="Enter text"
      />,
    );
    const errorMsg = screen.getByRole("alert");
    expect(errorMsg).toHaveTextContent("This field is required");
  });

  it("links textarea to error message via aria-describedby", () => {
    const { container } = render(
      <Textarea
        error
        errorMessage="Invalid input"
        errorId="field-error"
        placeholder="Enter text"
      />,
    );
    const textarea = container.querySelector("textarea");
    expect(textarea).toHaveAttribute("aria-describedby", "field-error");
  });

  it("does not render error message when error is not set", () => {
    render(
      <Textarea
        errorMessage="Should not appear"
        errorId="hidden-error"
        placeholder="Enter text"
      />,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error message has aria-live=polite", () => {
    render(
      <Textarea
        error
        errorMessage="Validation failed"
        errorId="live-error"
        placeholder="Enter text"
      />,
    );
    const errorMsg = screen.getByRole("alert");
    expect(errorMsg).toHaveAttribute("aria-live", "polite");
  });

  it("passes through standard textarea attributes", () => {
    const { container } = render(
      <Textarea placeholder="Type here..." rows={5} disabled name="notes" />,
    );
    const textarea = container.querySelector("textarea");
    expect(textarea).toHaveAttribute("placeholder", "Type here...");
    expect(textarea).toHaveAttribute("rows", "5");
    expect(textarea).toBeDisabled();
    expect(textarea).toHaveAttribute("name", "notes");
  });
});
