import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/help/helpers", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/components/help/helpers")>();

  return {
    ...actual,
    FAQ: [
      {
        q: "Can answer text render markup?",
        a: "Evidence <img src=x onerror=alert(1)> citations remain text.",
      },
    ],
    HELP_SECTION_SEARCH_TERMS: {
      ...actual.HELP_SECTION_SEARCH_TERMS,
      faq: ["FAQ"],
    },
  };
});

import { FaqCard } from "@/components/help/faq-card";

describe("FaqCard", () => {
  it("renders highlighted answer content as text instead of injected HTML", () => {
    render(<FaqCard query="" />);

    fireEvent.click(
      screen.getByRole("button", { name: "Can answer text render markup?" }),
    );

    expect(
      screen.getByText(
        "Evidence <img src=x onerror=alert(1)> citations remain text.",
      ),
    ).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
