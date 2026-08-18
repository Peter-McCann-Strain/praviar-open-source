import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  act,
} from "@testing-library/react";
import { CitationSuperscript } from "@/components/report/citation-superscript";
import type { CitationRef } from "@/types/citation";

vi.mock("motion/react", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

const citation: CitationRef = {
  index: 1,
  patentId: "US0000000001A1",
  claimNumber: 3,
  text: "A method of fermenting succinic acid using modified microorganisms",
  section: "patent:US0000000001A1",
  url: "https://patents.google.com/patent/US0000000001A1",
};

describe("CitationSuperscript", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("opens on hover and closes on mouse leave", async () => {
    render(<CitationSuperscript index={1} citation={citation} />);

    const trigger = screen.getByRole("button", { name: "Citation 1" });
    expect(trigger).toHaveClass("min-h-11", "min-w-11");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    fireEvent.mouseEnter(trigger);
    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toBeInTheDocument();
    expect(screen.getByText("US0000000001A1")).toBeInTheDocument();
    expect(screen.getByText("Claim 3")).toBeInTheDocument();

    fireEvent.mouseLeave(trigger);
    await act(async () => {
      vi.advanceTimersByTime(100);
    });

    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("invokes the click handler from both the superscript and the tooltip source link", async () => {
    const onClick = vi.fn();
    render(
      <CitationSuperscript index={7} citation={citation} onClick={onClick} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Citation 7" }));
    expect(onClick).toHaveBeenCalledWith(7);

    const trigger = screen.getByRole("button", { name: "Citation 7" });
    fireEvent.mouseEnter(trigger);
    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    fireEvent.click(screen.getByRole("button", { name: "View source" }));
    expect(onClick).toHaveBeenCalledTimes(2);
    expect(onClick).toHaveBeenLastCalledWith(7);
  });
});
