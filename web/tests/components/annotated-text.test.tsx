import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AnnotatedText } from "@/components/report/annotated-text";
import type { CitationRef } from "@/types/citation";

describe("AnnotatedText", () => {
  it("renders plain text when no markers present", () => {
    render(<AnnotatedText text="No citations here." />);
    expect(screen.getByText("No citations here.")).toBeInTheDocument();
  });

  it("renders citation superscripts for [n] markers", () => {
    render(<AnnotatedText text="See patent [1] for details." />);
    expect(screen.getByText("See patent")).toBeInTheDocument();
    expect(screen.getByText("for details.")).toBeInTheDocument();
    expect(screen.getByLabelText("Citation 1")).toBeInTheDocument();
  });

  it("renders multiple citation superscripts", () => {
    render(<AnnotatedText text="Claims [1] and [2] are relevant." />);
    expect(screen.getByLabelText("Citation 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Citation 2")).toBeInTheDocument();
  });

  it("calls onCitationClick when a citation is clicked", () => {
    const onClick = vi.fn();
    render(
      <AnnotatedText
        text="See patent [1] details."
        onCitationClick={onClick}
      />,
    );
    screen.getByLabelText("Citation 1").click();
    expect(onClick).toHaveBeenCalledWith(1);
  });

  it("applies custom className", () => {
    const { container } = render(
      <AnnotatedText text="Test" className="custom-class" />,
    );
    expect(container.querySelector(".custom-class")).toBeInTheDocument();
  });

  it("passes citation data to superscripts", () => {
    const citations = new Map<number, CitationRef>([
      [
        1,
        {
          index: 1,
          patentId: "US0000000001A1",
          text: "A fermentation process...",
          section: "patent:US0000000001A1",
        },
      ],
    ]);
    render(
      <AnnotatedText
        text="The patent [1] covers this."
        citations={citations}
      />,
    );
    // The superscript should be rendered with the citation data
    const citButton = screen.getByLabelText("Citation 1");
    expect(citButton).toBeInTheDocument();
    expect(citButton).toHaveTextContent("1");
  });
});
