import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ColumnDef } from "@tanstack/react-table";
import { describe, expect, it, vi } from "vitest";
import { DataTable, getSelectedRows } from "@/components/ui/data-table";

interface TestRow {
  name: string;
  owner: string;
  status: string;
}

const rows: TestRow[] = [
  { name: "Alpha", owner: "Fictional Meridian", status: "active" },
  { name: "Beta", owner: "Fictional Atlas", status: "queued" },
  { name: "Gamma", owner: "DSM", status: "done" },
  { name: "Delta", owner: "Fictional Nova", status: "done" },
  { name: "Epsilon", owner: "Fictional Meridian", status: "queued" },
  { name: "Zeta", owner: "Fictional Atlas", status: "active" },
];

const columns: ColumnDef<TestRow>[] = [
  {
    id: "select",
    header: () => <span>Select</span>,
    enableSorting: false,
    enableHiding: false,
    cell: ({ row }) => (
      <input
        type="checkbox"
        aria-label={`Select ${row.original.name}`}
        checked={row.getIsSelected()}
        onChange={row.getToggleSelectedHandler()}
      />
    ),
  },
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => row.original.name,
  },
  {
    accessorKey: "owner",
    header: "Owner",
    cell: ({ row }) => row.original.owner,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => row.original.status,
  },
];

describe("DataTable", () => {
  it("filters rows with the global search input", async () => {
    render(
      <DataTable
        columns={columns}
        data={rows}
        defaultPageSize={10}
        enableRowSelection
      />,
    );

    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search...")).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", { name: "Sort Name ascending" }),
    ).toHaveClass("min-h-11");

    fireEvent.change(screen.getByPlaceholderText("Search..."), {
      target: { value: "fictional atlas" },
    });

    await waitFor(() => {
      expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
      expect(screen.getByText("Beta")).toBeInTheDocument();
      expect(screen.getByText("Zeta")).toBeInTheDocument();
    });
  });

  it("toggles column visibility from the columns menu", async () => {
    render(<DataTable columns={columns} data={rows} defaultPageSize={10} />);

    expect(screen.getByText("Owner")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Columns" }));
    expect(screen.getByRole("button", { name: "Columns" })).toHaveClass(
      "min-h-11",
    );
    const ownerToggle = screen.getByRole("menuitemcheckbox", {
      name: "Owner",
    });

    expect(ownerToggle).toHaveAttribute("aria-checked", "true");
    expect(ownerToggle).toHaveClass("min-h-11");

    fireEvent.click(ownerToggle);

    expect(ownerToggle).toHaveAttribute("aria-checked", "false");

    await waitFor(() => {
      expect(
        screen.queryByRole("columnheader", { name: "Owner" }),
      ).not.toBeInTheDocument();
      expect(screen.queryByText("Fictional Meridian")).not.toBeInTheDocument();
    });
  });

  it("paginates rows and lets the user change page size", async () => {
    render(<DataTable columns={columns} data={rows} defaultPageSize={2} />);

    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Gamma")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: "Go to next page" })).toHaveClass(
      "min-h-11",
      "min-w-11",
    );

    fireEvent.click(screen.getByRole("button", { name: "Go to next page" }));

    await waitFor(() => {
      expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
      expect(screen.getByText("Gamma")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "25" },
    });

    await waitFor(() => {
      expect(screen.getByText("Page 1 of 1")).toBeInTheDocument();
      expect(screen.getByText("Zeta")).toBeInTheDocument();
    });
  });

  it("reports selected rows through the callback", async () => {
    const onRowSelectionChange = vi.fn();

    render(
      <DataTable
        columns={columns}
        data={rows}
        defaultPageSize={10}
        enableRowSelection
        onRowSelectionChange={onRowSelectionChange}
      />,
    );

    fireEvent.click(screen.getByLabelText("Select Alpha"));

    await waitFor(() => {
      expect(onRowSelectionChange).toHaveBeenLastCalledWith([rows[0]]);
      expect(screen.getByText("1 selected")).toBeInTheDocument();
    });
  });
});

describe("getSelectedRows", () => {
  it("maps selected row keys back to the original data array", () => {
    expect(getSelectedRows(rows, { 1: true, 4: true })).toEqual([
      rows[1],
      rows[4],
    ]);
  });
});
