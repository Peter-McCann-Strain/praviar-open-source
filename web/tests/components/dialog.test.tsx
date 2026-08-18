import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  CommandDialog,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

describe("Dialog", () => {
  it("applies the shared viewport-safe shell", () => {
    render(
      <Dialog open onOpenChange={vi.fn()}>
        <DialogContent>
          <DialogTitle>Review action</DialogTitle>
          <DialogDescription>Confirm this change.</DialogDescription>
        </DialogContent>
      </Dialog>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toContain("max-h-[calc(100dvh-2rem)]");
    expect(dialog.className).toContain("w-[calc(100vw-2rem)]");
    expect(dialog.className).toContain("overflow-y-auto");
    expect(dialog.className).toContain(
      "motion-reduce:data-[state=open]:animate-none",
    );
  });

  it("keeps the close control at a stable touch target size", () => {
    render(
      <Dialog open onOpenChange={vi.fn()}>
        <DialogContent>
          <DialogTitle>Dismissible dialog</DialogTitle>
          <DialogDescription>
            Verify the close control remains accessible.
          </DialogDescription>
        </DialogContent>
      </Dialog>,
    );

    const close = screen.getByRole("button", { name: "Close" });
    expect(close.className).toContain("h-11");
    expect(close.className).toContain("w-11");
    expect(close.className).toContain("focus-visible:ring-brand-primary/70");
  });

  it("gives the command palette an accessible description", () => {
    render(
      <CommandDialog open onOpenChange={vi.fn()}>
        <div>Command content</div>
      </CommandDialog>,
    );

    const dialog = screen.getByRole("dialog");
    const description = screen.getByText(
      "Search analyses and navigate to Praviar workspace actions.",
    );
    expect(dialog).toHaveAttribute("aria-describedby", description.id);
  });

  it("uses a full-width bottom sheet on narrow command-palette viewports", () => {
    render(
      <CommandDialog open onOpenChange={vi.fn()}>
        <div>Command content</div>
      </CommandDialog>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveClass(
      "max-sm:bottom-0",
      "max-sm:left-0",
      "max-sm:right-0",
      "max-sm:top-auto",
      "max-sm:w-full",
      "max-sm:translate-x-0",
      "max-sm:translate-y-0",
      "max-sm:rounded-t-xl",
    );
  });

  it("keeps decorative separators out of the listbox ownership tree", () => {
    render(
      <CommandDialog open onOpenChange={vi.fn()}>
        <CommandList>
          <CommandSeparator />
        </CommandList>
      </CommandDialog>,
    );

    const separator = document.querySelector("[data-command-separator]");
    expect(separator).toHaveAttribute("role", "presentation");
    expect(separator).toHaveAttribute("aria-hidden", "true");
  });
});
