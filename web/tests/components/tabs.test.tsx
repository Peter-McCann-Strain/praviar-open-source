import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

describe("Tabs", () => {
  function renderTabs(defaultValue = "tab1") {
    return render(
      <Tabs defaultValue={defaultValue}>
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
          <TabsTrigger value="tab3" disabled>
            Tab 3
          </TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content 1</TabsContent>
        <TabsContent value="tab2">Content 2</TabsContent>
        <TabsContent value="tab3">Content 3</TabsContent>
      </Tabs>,
    );
  }

  it("renders tabs with default selection", () => {
    renderTabs();
    expect(screen.getByText("Content 1")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tab 1" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });

  it("tab 2 starts inactive when tab 1 is default", () => {
    renderTabs();
    expect(screen.getByRole("tab", { name: "Tab 2" })).toHaveAttribute(
      "data-state",
      "inactive",
    );
    expect(screen.getByRole("tab", { name: "Tab 1" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });

  it("respects disabled state", () => {
    renderTabs();
    const disabledTab = screen.getByRole("tab", { name: "Tab 3" });
    expect(disabledTab).toBeDisabled();
  });

  it("renders correct number of tabs", () => {
    renderTabs();
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
  });

  it("starts with specified default value", () => {
    renderTabs("tab2");
    expect(screen.getByText("Content 2")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tab 2" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });
});
