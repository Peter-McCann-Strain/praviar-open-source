import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { createRef } from "react";
import { Input } from "@/components/ui/input";

describe("Input", () => {
  describe("rendering", () => {
    it("renders an input element", () => {
      render(<Input />);
      expect(screen.getByRole("textbox")).toBeInTheDocument();
    });

    it("renders with a placeholder", () => {
      render(<Input placeholder="Enter compound name" />);
      expect(
        screen.getByPlaceholderText("Enter compound name"),
      ).toBeInTheDocument();
    });

    it("renders with a default value", () => {
      render(<Input defaultValue="aspirin" />);
      expect(screen.getByDisplayValue("aspirin")).toBeInTheDocument();
    });

    it("renders with the correct type", () => {
      render(<Input type="email" data-testid="email-input" />);
      expect(screen.getByTestId("email-input")).toHaveAttribute(
        "type",
        "email",
      );
    });

    it("renders with the correct type for password", () => {
      render(<Input type="password" data-testid="pw-input" />);
      expect(screen.getByTestId("pw-input")).toHaveAttribute(
        "type",
        "password",
      );
    });
  });

  describe("onChange handler", () => {
    it("fires onChange when user types", () => {
      const handleChange = vi.fn();
      render(<Input onChange={handleChange} />);
      const input = screen.getByRole("textbox");
      fireEvent.change(input, { target: { value: "aspirin" } });
      expect(handleChange).toHaveBeenCalledOnce();
    });

    it("receives the new value in the event", () => {
      const handleChange = vi.fn();
      render(<Input onChange={handleChange} />);
      const input = screen.getByRole("textbox");
      fireEvent.change(input, { target: { value: "ibuprofen" } });
      expect(handleChange.mock.calls[0][0].target.value).toBe("ibuprofen");
    });
  });

  describe("disabled state", () => {
    it("renders as disabled when disabled prop is true", () => {
      render(<Input disabled />);
      expect(screen.getByRole("textbox")).toBeDisabled();
    });

    it("applies disabled styling class", () => {
      const { container } = render(<Input disabled />);
      const input = container.querySelector("input")!;
      expect(input.className).toContain("disabled:cursor-not-allowed");
      expect(input.className).toContain("disabled:opacity-50");
    });

    it("is not disabled by default", () => {
      render(<Input />);
      expect(screen.getByRole("textbox")).not.toBeDisabled();
    });
  });

  describe("className prop", () => {
    it("passes custom className", () => {
      const { container } = render(<Input className="my-input" />);
      const input = container.querySelector("input")!;
      expect(input.className).toContain("my-input");
    });

    it("merges custom className with base classes", () => {
      const { container } = render(<Input className="extra-class" />);
      const input = container.querySelector("input")!;
      expect(input.className).toContain("extra-class");
      expect(input.className).toContain("rounded-lg");
    });
  });

  describe("ref forwarding", () => {
    it("forwards ref to the input element", () => {
      const ref = createRef<HTMLInputElement>();
      render(<Input ref={ref} />);
      expect(ref.current).toBeInstanceOf(HTMLInputElement);
    });

    it("allows programmatic focus via ref", () => {
      const ref = createRef<HTMLInputElement>();
      render(<Input ref={ref} />);
      ref.current!.focus();
      expect(document.activeElement).toBe(ref.current);
    });
  });

  describe("base styling", () => {
    it("includes base utility classes", () => {
      const { container } = render(<Input />);
      const input = container.querySelector("input")!;
      expect(input.className).toContain("flex");
      expect(input.className).toContain("h-11");
      expect(input.className).toContain("w-full");
      expect(input.className).toContain("rounded-lg");
      expect(input.className).toContain("border");
      expect(input.className).toContain("text-sm");
      expect(input.className).toContain("focus:ring-brand-primary/70");
    });
  });

  describe("HTML attributes pass-through", () => {
    it("supports name attribute", () => {
      render(<Input name="compound" data-testid="named" />);
      expect(screen.getByTestId("named")).toHaveAttribute("name", "compound");
    });

    it("supports aria-label for accessibility", () => {
      render(<Input aria-label="Search compounds" />);
      expect(screen.getByLabelText("Search compounds")).toBeInTheDocument();
    });

    it("supports maxLength", () => {
      render(<Input maxLength={100} data-testid="max" />);
      expect(screen.getByTestId("max")).toHaveAttribute("maxLength", "100");
    });
  });
});
