import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Button } from "@/components/ui/button";

describe("Button", () => {
  describe("rendering", () => {
    it("renders with text content", () => {
      render(<Button>Click me</Button>);
      expect(
        screen.getByRole("button", { name: "Click me" }),
      ).toBeInTheDocument();
    });

    it("renders as a button element by default", () => {
      render(<Button>Submit</Button>);
      const btn = screen.getByRole("button");
      expect(btn.tagName).toBe("BUTTON");
      expect(btn).toHaveAttribute("type", "button");
    });

    it("preserves an explicit submit type", () => {
      render(<Button type="submit">Submit</Button>);
      expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
    });
  });

  describe("variants", () => {
    it("applies default variant classes", () => {
      const { container } = render(<Button variant="default">Default</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("bg-brand-primary-dim");
      expect(btn.className).toContain("text-[var(--brand-paper)]");
    });

    it("applies destructive variant classes", () => {
      const { container } = render(
        <Button variant="destructive">Delete</Button>,
      );
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("bg-error-emphasis");
      expect(btn.className).toContain("text-[var(--brand-paper)]");
    });

    it("applies outline variant classes", () => {
      const { container } = render(<Button variant="outline">Outline</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("border");
      expect(btn.className).toContain("bg-transparent");
    });

    it("applies secondary variant classes", () => {
      const { container } = render(
        <Button variant="secondary">Secondary</Button>,
      );
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("bg-[var(--surface-active)]");
    });

    it("applies ghost variant classes", () => {
      const { container } = render(<Button variant="ghost">Ghost</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("text-[var(--text-secondary)]");
      expect(btn.className).not.toContain("bg-brand-primary-dim");
    });

    it("applies link variant classes", () => {
      const { container } = render(<Button variant="link">Link</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("text-brand-primary");
      expect(btn.className).toContain("underline-offset-4");
    });

    it("uses default variant when none specified", () => {
      const { container } = render(<Button>No variant</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("bg-brand-primary-dim");
    });
  });

  describe("sizes", () => {
    it("applies default size classes", () => {
      const { container } = render(
        <Button size="default">Default size</Button>,
      );
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("h-10");
      expect(btn.className).toContain("px-4");
      expect(btn.className).toContain("[@media(pointer:coarse)]:min-h-11");
      expect(btn.className).toContain("[@media(pointer:coarse)]:min-w-11");
    });

    it("applies sm size classes", () => {
      const { container } = render(<Button size="sm">Small</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("h-8");
      expect(btn.className).toContain("px-3");
      expect(btn.className).toContain("text-xs");
      expect(btn.className).toContain("[@media(pointer:coarse)]:min-h-11");
      expect(btn.className).toContain("[@media(pointer:coarse)]:min-w-11");
    });

    it("applies lg size classes", () => {
      const { container } = render(<Button size="lg">Large</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("h-11");
      expect(btn.className).toContain("px-6");
      expect(btn.className).toContain("text-base");
    });

    it("applies icon size classes", () => {
      const { container } = render(<Button size="icon">X</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("h-10");
      expect(btn.className).toContain("w-10");
      expect(btn.className).toContain("[@media(pointer:coarse)]:h-11");
      expect(btn.className).toContain("[@media(pointer:coarse)]:w-11");
    });

    it("uses default size when none specified", () => {
      const { container } = render(<Button>No size</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("h-10");
      expect(btn.className).toContain("px-4");
    });
  });

  describe("click handler", () => {
    it("fires onClick when clicked", () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>Click</Button>);
      fireEvent.click(screen.getByRole("button"));
      expect(handleClick).toHaveBeenCalledOnce();
    });

    it("fires onClick multiple times on multiple clicks", () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>Click</Button>);
      const btn = screen.getByRole("button");
      fireEvent.click(btn);
      fireEvent.click(btn);
      fireEvent.click(btn);
      expect(handleClick).toHaveBeenCalledTimes(3);
    });
  });

  describe("disabled state", () => {
    it("renders with disabled attribute", () => {
      render(<Button disabled>Disabled</Button>);
      expect(screen.getByRole("button")).toBeDisabled();
    });

    it("applies disabled opacity class", () => {
      const { container } = render(<Button disabled>Disabled</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("disabled:opacity-50");
    });

    it("applies pointer-events-none class when disabled", () => {
      const { container } = render(<Button disabled>Disabled</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("disabled:pointer-events-none");
    });

    it("does not fire onClick when disabled", () => {
      const handleClick = vi.fn();
      render(
        <Button disabled onClick={handleClick}>
          Disabled
        </Button>,
      );
      fireEvent.click(screen.getByRole("button"));
      expect(handleClick).not.toHaveBeenCalled();
    });
  });

  describe("asChild composition", () => {
    it("renders children as the root element via Slot when asChild is true", () => {
      const { container } = render(
        <Button asChild>
          <a href="/test">Link Button</a>
        </Button>,
      );
      const anchor = container.querySelector("a");
      expect(anchor).toBeInTheDocument();
      expect(anchor!.getAttribute("href")).toBe("/test");
      expect(anchor).not.toHaveAttribute("type");
      expect(anchor!.textContent).toBe("Link Button");
    });

    it("does not render a button element when asChild is true", () => {
      render(
        <Button asChild>
          <a href="/test">Link Button</a>
        </Button>,
      );
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    it("applies button variant classes to the child element", () => {
      const { container } = render(
        <Button asChild variant="destructive">
          <a href="/delete">Delete</a>
        </Button>,
      );
      const anchor = container.querySelector("a")!;
      expect(anchor.className).toContain("bg-error-emphasis");
    });
  });

  describe("className prop", () => {
    it("merges custom className with variant classes", () => {
      const { container } = render(
        <Button className="my-custom-class">Custom</Button>,
      );
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("my-custom-class");
      expect(btn.className).toContain("bg-brand-primary-dim");
    });
  });

  describe("base styles", () => {
    it("includes base utility classes", () => {
      const { container } = render(<Button>Base</Button>);
      const btn = container.querySelector("button")!;
      expect(btn.className).toContain("inline-flex");
      expect(btn.className).toContain("items-center");
      expect(btn.className).toContain("rounded-lg");
      expect(btn.className).toContain("text-sm");
      expect(btn.className).toContain("font-medium");
      expect(btn.className).toContain("cursor-pointer");
    });
  });
});
