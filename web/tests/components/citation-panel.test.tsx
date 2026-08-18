import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CitationPanel } from "@/components/report/citation-panel";
import type { CitationRef } from "@/types/citation";

vi.mock("motion/react", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    aside: ({ children, ...props }: any) => (
      <aside {...props}>{children}</aside>
    ),
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

const mockCitation: CitationRef = {
  index: 1,
  patentId: "US0000000001A1",
  claimNumber: 3,
  elementNumber: 2,
  text: "A method of fermenting succinic acid using modified microorganisms",
  section: "patent:US0000000001A1",
  url: "https://patents.google.com/patent/US0000000001A1",
};

describe("CitationPanel", () => {
  it("renders nothing when citation is null", () => {
    const { container } = render(
      <CitationPanel citation={null} onClose={vi.fn()} />,
    );
    expect(container.querySelector("aside")).toBeNull();
  });

  it("renders panel with citation data", () => {
    render(<CitationPanel citation={mockCitation} onClose={vi.fn()} />);
    expect(screen.getByText("US0000000001A1")).toHaveClass(
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("Claim 3")).toBeInTheDocument();
    expect(screen.getByText("Element 2")).toBeInTheDocument();
    expect(screen.getByText(/fermenting succinic acid/)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
  });

  it("portals the dialog to the document body above dashboard stacking contexts", () => {
    const { container } = render(
      <CitationPanel citation={mockCitation} onClose={vi.fn()} />,
    );

    const dialog = screen.getByRole("dialog", { name: "Citation source" });
    const close = screen.getByRole("button", { name: "Close citation panel" });

    expect(container).not.toContainElement(dialog);
    expect(dialog.parentElement).toBe(document.body);
    expect(dialog).toContainElement(close);
    expect(dialog).toHaveClass("fixed", "z-[70]", "sm:top-0");
  });

  it("shows Cited Passage section", () => {
    render(<CitationPanel citation={mockCitation} onClose={vi.fn()} />);
    expect(screen.getByText("Cited Passage")).toBeInTheDocument();
  });

  it("shows only explicit report identity and research boundary context", () => {
    render(
      <CitationPanel
        citation={{
          ...mockCitation,
          patentId: "XX-FICTION-0001-A1",
          text: "A fictional composition comprising Example Molecule Alpha.",
        }}
        report={{
          compound: { name: "Example Molecule Alpha" },
          disclaimer:
            "Fictional research preview for software demonstration only. Not legal advice or an FTO opinion.",
        }}
        onClose={vi.fn()}
      />,
    );

    const context = screen.getByRole("note", {
      name: "Citation report context",
    });
    expect(context).toHaveTextContent("Example Molecule Alpha");
    expect(context).toHaveTextContent("research preview");
    expect(context).toHaveTextContent("Not legal advice");
  });

  it("does not fabricate report context when boundary fields are absent", () => {
    render(
      <CitationPanel
        citation={mockCitation}
        report={{ compound: { name: "Example Molecule Alpha" } }}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.queryByTestId("citation-report-context"),
    ).not.toBeInTheDocument();
  });

  it("calls onClose when close button clicked", () => {
    const onClose = vi.fn();
    render(<CitationPanel citation={mockCitation} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("Close citation panel"));
    expect(onClose).toHaveBeenCalled();
    expect(screen.getByLabelText("Close citation panel")).toHaveClass(
      "h-11",
      "w-11",
    );
  });

  it("traps forward and reverse tab focus inside the modal panel", () => {
    render(
      <CitationPanel
        citation={mockCitation}
        onClose={vi.fn()}
        onOpenPatent={vi.fn()}
      />,
    );

    const dialog = screen.getByRole("dialog", { name: "Citation source" });
    const close = screen.getByRole("button", { name: "Close citation panel" });
    const external = screen.getByRole("link", { name: "External" });

    external.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(close).toHaveFocus();

    close.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(external).toHaveFocus();
  });

  it("renders Open in Patent Drawer button when patent and handler provided", () => {
    const onOpenPatent = vi.fn();
    render(
      <CitationPanel
        citation={mockCitation}
        onClose={vi.fn()}
        onOpenPatent={onOpenPatent}
      />,
    );
    const button = screen.getByText("Open in Patent Drawer");
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass("min-h-11");
    fireEvent.click(button);
    expect(onOpenPatent).toHaveBeenCalledWith("US0000000001A1");
  });

  it("closes the panel after opening a patent drawer", () => {
    const onOpenPatent = vi.fn();
    const onClose = vi.fn();

    render(
      <CitationPanel
        citation={mockCitation}
        onClose={onClose}
        onOpenPatent={onOpenPatent}
      />,
    );

    fireEvent.click(screen.getByText("Open in Patent Drawer"));

    expect(onOpenPatent).toHaveBeenCalledWith("US0000000001A1");
    expect(onClose).toHaveBeenCalled();
  });

  it("renders external link when URL provided", () => {
    render(<CitationPanel citation={mockCitation} onClose={vi.fn()} />);
    expect(screen.getByText("External").closest("a")).toHaveClass("min-h-11");
  });

  it("shows source text with highlight when provided", () => {
    render(
      <CitationPanel
        citation={mockCitation}
        sourceText="Prior art includes: A method of fermenting succinic acid using modified microorganisms, which was published in 2020."
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("Full Source")).toBeInTheDocument();
  });

  it("wraps long citation, source, and section strings without horizontal overflow", () => {
    const longCitation = {
      ...mockCitation,
      patentId: `US${"1234567890".repeat(18)}B2`,
      text: `Claim passage ${"continuousfermentationneutralization".repeat(20)}`,
      section: `patent:${"US20260345678A1".repeat(8)}:claim:${"element".repeat(20)}`,
    };
    const sourceText = `Source context ${"InChI=1S/C4H6O4NoNaturalBreak".repeat(20)}`;

    render(
      <CitationPanel
        citation={longCitation}
        sourceText={sourceText}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText(longCitation.patentId)).toHaveClass(
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longCitation.text)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(sourceText)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(`Source: ${longCitation.section}`)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
  });

  it("shows citation index badge", () => {
    render(<CitationPanel citation={mockCitation} onClose={vi.fn()} />);
    // The index badge shows "1"
    expect(screen.getByText("1")).toBeInTheDocument();
  });
});
