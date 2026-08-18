import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "@/components/ui/button";

describe("Button loading state", () => {
  it("renders children normally when not loading", () => {
    render(<Button>Submit</Button>);
    expect(screen.getByRole("button", { name: "Submit" })).toBeInTheDocument();
  });

  it("shows spinner when loading", () => {
    render(<Button loading>Submit</Button>);
    const button = screen.getByRole("button");
    // Loader2 renders as an SVG with animate-spin class
    const spinner = button.querySelector("svg.animate-spin");
    expect(spinner).toBeTruthy();
  });

  it("is disabled when loading", () => {
    render(<Button loading>Submit</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("is disabled when disabled prop is true", () => {
    render(<Button disabled>Submit</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("shows both spinner and children when loading", () => {
    render(<Button loading>Save Changes</Button>);
    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("Save Changes");
    expect(button.querySelector("svg.animate-spin")).toBeTruthy();
  });

  it("does not show spinner when not loading", () => {
    render(<Button>Submit</Button>);
    const button = screen.getByRole("button");
    expect(button.querySelector("svg.animate-spin")).toBeNull();
  });
});
