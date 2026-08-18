import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProductContextBrief } from "@/components/analysis-wizard/product-context-brief";
import { EMPTY_PRODUCT_CONTEXT } from "@/lib/product-context";
import type {
  MatterScopePreflightValue,
  ProductContextValue,
} from "@/types/pipeline";

const FORMULATION_SCOPE: MatterScopePreflightValue = {
  assetTypeHint: "formulation",
  developmentStage: "clinical",
  intendedActions: ["formulation_review", "commercial_launch"],
};

function Harness() {
  const [value, setValue] = useState<ProductContextValue>({
    ...EMPTY_PRODUCT_CONTEXT,
  });

  return (
    <ProductContextBrief
      matterScope={FORMULATION_SCOPE}
      value={value}
      onChange={setValue}
    />
  );
}

describe("ProductContextBrief", () => {
  it("blocks launch-scoped context gaps until facts or unknowns are explicit", () => {
    render(<Harness />);

    expect(
      screen.getByRole("region", { name: "Product context intake" }),
    ).toBeInTheDocument();
    const disclosure = screen.getByTestId("product-context-mobile-disclosure");
    expect(disclosure).toHaveClass("sm:block");
    expect(within(disclosure).getByText(/0 captured · \d+ open/)).toBeVisible();
    expect(
      screen.getByRole("note", {
        name: "Reviewer-ready product context brief",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Product facts that change FTO"),
    ).toBeInTheDocument();
    expect(screen.getByText(/0 facts captured/i)).toBeInTheDocument();
    expect(screen.getByText(/Launch blocked:/i)).toBeInTheDocument();
    expect(screen.getByText(/Enter facts or "Unknown"/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Product or program"), {
      target: { value: "PRV-142 oral tablet" },
    });
    fireEvent.change(screen.getByLabelText("Dosage form"), {
      target: { value: "Film-coated tablet" },
    });
    fireEvent.change(screen.getByLabelText("Route"), {
      target: { value: "Oral" },
    });
    fireEvent.change(screen.getByLabelText("Strength"), {
      target: { value: "200 mg" },
    });
    fireEvent.change(screen.getByLabelText("Salt / polymorph"), {
      target: { value: "Unknown" },
    });
    fireEvent.change(screen.getByLabelText("Key excipients"), {
      target: { value: "Lactose, HPMC" },
    });
    fireEvent.change(screen.getByLabelText("Indication"), {
      target: { value: "Unknown" },
    });
    fireEvent.change(screen.getByLabelText("Commercial action"), {
      target: { value: "US launch diligence before term sheet" },
    });
    fireEvent.change(screen.getByLabelText("Commercial territories"), {
      target: { value: "US, EP" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add act" }));
    fireEvent.change(screen.getByLabelText("Act 1 jurisdiction"), {
      target: { value: "US" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 start date"), {
      target: { value: "2027-03-01" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 actor"), {
      target: { value: "Praviar Pharma Ltd" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 instrumentality"), {
      target: { value: "PRV-142 oral tablet" },
    });

    expect(screen.getByText(/10 facts captured/i)).toBeInTheDocument();
    expect(screen.getAllByText("Film-coated tablet").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Oral").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("200 mg")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Lactose, HPMC")).toBeInTheDocument();
    expect(screen.getByText(/Core context ready/i)).toBeInTheDocument();
  });

  it("keeps denied and hypothetical acts visibly non-governing", () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Add act" }));
    fireEvent.change(screen.getByLabelText("Act 1 status"), {
      target: { value: "denied" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 jurisdiction"), {
      target: { value: "US" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 start date"), {
      target: { value: "2027-03-01" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 actor"), {
      target: { value: "Praviar Pharma Ltd" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 instrumentality"), {
      target: { value: "PRV-142 oral tablet" },
    });

    expect(screen.getByText(/Launch blocked:/i)).toBeInTheDocument();
    expect(
      screen.getAllByText(/Structured accused acts/i).length,
    ).toBeGreaterThan(0);
  });

  it("captures strict submission-use facts and shows missing receipt state", () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Add act" }));
    fireEvent.change(screen.getByLabelText("Act 1 type"), {
      target: { value: "regulatory_submission" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 target product identity"), {
      target: { value: "ibuprofen" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 proposed indication"), {
      target: { value: "Pain" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 proposed label use"), {
      target: { value: "200 mg orally for pain" },
    });
    fireEvent.change(screen.getByLabelText("Act 1 label carve-out state"), {
      target: { value: "none" },
    });

    expect(
      screen.getByText(
        /Not attached. The submission cannot establish a method-of-use claim match/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Act 1 liability theory")).toBeDisabled();
    expect(screen.getByLabelText("Act 1 liability theory")).toHaveValue(
      "artificial_infringement",
    );
  });
});
