import { createRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MonitorsPageHeader } from "@/components/monitors/page-header";

describe("MonitorsPageHeader", () => {
  it("uses the shared app surface header and routes create actions", () => {
    const onCreateClick = vi.fn();
    const createButtonRef = createRef<HTMLButtonElement>();

    render(
      <MonitorsPageHeader
        createButtonRef={createButtonRef}
        onCreateClick={onCreateClick}
      />,
    );

    expect(screen.getByTestId("monitors-app-surface-header")).toHaveAttribute(
      "data-praviar-app-surface-header",
    );
    expect(screen.getByText("Patent monitoring workspace")).toBeInTheDocument();
    expect(screen.getByText("Landscape change")).toBeInTheDocument();
    expect(screen.getByText("Scheduled watches")).toBeInTheDocument();
    expect(screen.getByText("Human handoff")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "New Monitor" }));

    expect(onCreateClick).toHaveBeenCalledTimes(1);
    expect(createButtonRef.current).toBeInstanceOf(HTMLButtonElement);
  });
});
