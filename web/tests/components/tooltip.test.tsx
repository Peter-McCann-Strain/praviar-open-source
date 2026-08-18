import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip";

describe("Tooltip", () => {
  describe("exports", () => {
    it("exports Tooltip component", () => {
      expect(Tooltip).toBeDefined();
    });

    it("exports TooltipTrigger component", () => {
      expect(TooltipTrigger).toBeDefined();
    });

    it("exports TooltipContent component", () => {
      expect(TooltipContent).toBeDefined();
    });

    it("exports TooltipProvider component", () => {
      expect(TooltipProvider).toBeDefined();
    });
  });

  describe("rendering", () => {
    it("renders trigger content", () => {
      render(
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>Hover me</TooltipTrigger>
            <TooltipContent>Tooltip text</TooltipContent>
          </Tooltip>
        </TooltipProvider>,
      );
      expect(screen.getByText("Hover me")).toBeInTheDocument();
    });

    it("renders trigger as a button by default", () => {
      render(
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>Click target</TooltipTrigger>
            <TooltipContent>Info</TooltipContent>
          </Tooltip>
        </TooltipProvider>,
      );
      const trigger = screen.getByText("Click target");
      expect(trigger.tagName).toBe("BUTTON");
    });
  });

  describe("TooltipContent", () => {
    it("has the correct displayName", () => {
      expect(TooltipContent.displayName).toBe("TooltipContent");
    });

    it("accepts a custom className", () => {
      render(
        <TooltipProvider>
          <Tooltip defaultOpen>
            <TooltipTrigger>Trigger</TooltipTrigger>
            <TooltipContent className="custom-tooltip-class">
              Content
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>,
      );
      // Radix renders tooltip text twice (visible + accessible span), so use getAllByText
      const elements = screen.getAllByText("Content");
      expect(elements.length).toBeGreaterThanOrEqual(1);
      const contentEl = elements.find((el) =>
        el.className.includes("custom-tooltip-class"),
      );
      expect(contentEl).toBeDefined();
    });

    it("accepts a custom sideOffset prop without error", () => {
      // Verifies the component accepts sideOffset without throwing
      expect(() =>
        render(
          <TooltipProvider>
            <Tooltip defaultOpen>
              <TooltipTrigger>Trigger</TooltipTrigger>
              <TooltipContent sideOffset={12}>Offset content</TooltipContent>
            </Tooltip>
          </TooltipProvider>,
        ),
      ).not.toThrow();
    });
  });
});
