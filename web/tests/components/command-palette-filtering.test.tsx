import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NavigationCommandGroups } from "@/components/shared/command-palette";
import {
  Command,
  CommandInput,
  CommandList,
  strictCommandFilter,
} from "@/components/ui/command";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ isLoaded: true, orgRole: "org:admin" }),
}));

vi.mock("@/hooks/use-analysis", () => ({
  useAnalyses: () => ({ data: undefined }),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => null,
}));

describe("command palette filtering", () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it.each([
    ["molecules", "Compounds"],
    ["claims", "Patents"],
    ["payments", "Credits & Billing"],
    ["sso", "Settings"],
    ["costs", "Cost & Usage"],
  ])("finds %s through the real cmdk filter", (query, expectedLabel) => {
    render(
      <Command label="Destination search" filter={strictCommandFilter}>
        <CommandInput />
        <CommandList>
          <NavigationCommandGroups
            orgRole="org:admin"
            applicationRole="admin"
            onNavigate={vi.fn()}
          />
        </CommandList>
      </Command>,
    );

    fireEvent.change(
      screen.getByRole("combobox", { name: "Destination search" }),
      {
        target: { value: query },
      },
    );

    expect(screen.getByText(expectedLabel)).toBeVisible();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("keeps member-only search results free of admin destinations", () => {
    render(
      <Command label="Destination search" filter={strictCommandFilter}>
        <CommandInput />
        <CommandList>
          <NavigationCommandGroups
            orgRole="org:member"
            applicationRole="scientist"
            onNavigate={vi.fn()}
          />
        </CommandList>
      </Command>,
    );

    fireEvent.change(
      screen.getByRole("combobox", { name: "Destination search" }),
      {
        target: { value: "costs" },
      },
    );

    expect(screen.queryByText("Cost & Usage")).not.toBeInTheDocument();
  });
});
