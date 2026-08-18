import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IdentityReviewCheckpoint } from "@/components/pipeline/identity-review-checkpoint";

const IDENTITY_CONTEXT: Record<string, unknown> = {
  schema_version: "identity-review/v1",
  checkpoint_id: "run-1:identity_review:1234567890abcdef",
  identity_fingerprint:
    "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
  original_input: "C[C@H](O)C(=O)OC",
  input_type: "smiles",
  comparison: {
    outcome: "normalized_match",
    submitted_value: "C[C@H](O)C(=O)OC",
    resolved_value: "COC(=O)[C@@H](C)O",
    detail:
      "The notation changed during canonicalization, but both strings resolve to the same graph.",
    requires_attention: false,
  },
  resolved_identity: {
    name: "Test chiral ester",
    compound_type: "small_molecule",
    source_authority: "PubChem",
    source_record_id: "CID 123",
    canonical_smiles: "COC(=O)[C@@H](C)O",
    inchi_key: "AAAAAAAAAAAAAA-BBBBBBBBBB-C",
    molecular_formula: "C5H10O3",
    molecular_weight: 118.13,
    cas_numbers: ["12345-67-8"],
    authoritative_record_present: true,
  },
  search_envelope: [
    {
      lane_id: "canonical_structure",
      label: "Canonical structure",
      values: ["COC(=O)[C@@H](C)O"],
      total_value_count: 1,
      sources: ["SureChEMBL", "PubChem"],
      enabled: true,
      purpose: "Exact and similarity structure retrieval.",
    },
    {
      lane_id: "stereo_stripped_structure",
      label: "Stereo-stripped structure",
      values: ["COC(=O)C(C)O"],
      total_value_count: 1,
      sources: ["SureChEMBL"],
      enabled: false,
      purpose: "Broaden retrieval to racemate or stereoisomer claim scope.",
    },
  ],
  variant_assessments: [
    {
      variant: "salt_or_product_form",
      label: "Salt / product form",
      status: "declared",
      declared_value: "Hydrochloride, Form A",
      search_effect: "A salt-stripped lane is available.",
      limitation: "The product declaration is user supplied.",
      requires_attention: false,
    },
    {
      variant: "stereochemistry",
      label: "Stereochemistry",
      status: "derived_search_form",
      derived_value: "COC(=O)C(C)O",
      search_effect: "A stereo-stripped lane is included.",
      limitation: "Individual stereoisomers are not enumerated.",
      requires_attention: true,
    },
    {
      variant: "tautomer",
      label: "Tautomers",
      status: "not_modeled",
      search_effect: "No tautomer-normalized lane is generated.",
      limitation: "Canonical SMILES is not proof of tautomer coverage.",
      requires_attention: true,
    },
    {
      variant: "prodrug",
      label: "Prodrug / active form",
      status: "candidate_detected",
      derived_value: "ester_prodrug",
      search_effect: "No activated structure is added.",
      limitation: "Motif detection is advisory.",
      requires_attention: true,
    },
  ],
  product_form_declaration: "Hydrochloride, Form A",
  approval_attestation:
    "I verified the resolved identity and accept the disclosed limitations.",
};

describe("IdentityReviewCheckpoint", () => {
  it("shows the authoritative resolution, exact envelope, and all variant limits", () => {
    render(
      <IdentityReviewCheckpoint
        data={IDENTITY_CONTEXT}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "Approve the resolved compound before search",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("PubChem")).toBeInTheDocument();
    expect(screen.getByText("CID 123")).toBeInTheDocument();
    expect(screen.getByText(/SHA-256 1234567890ab/i)).toBeInTheDocument();
    expect(screen.getByText("Normalized match")).toBeInTheDocument();
    expect(screen.getByText("Canonical structure")).toBeInTheDocument();
    expect(screen.getByText("Stereo-stripped structure")).toBeInTheDocument();
    expect(screen.getByText("Tautomers")).toBeInTheDocument();
    expect(screen.getByText("Not modeled")).toBeInTheDocument();
    expect(screen.getByText("Prodrug / active form")).toBeInTheDocument();
    expect(screen.getByText("Candidate detected")).toBeInTheDocument();
    expect(screen.getByText("1/2 lanes active")).toBeInTheDocument();
  });

  it("requires explicit attestation before approval", () => {
    const onApprove = vi.fn();

    render(
      <IdentityReviewCheckpoint
        data={IDENTITY_CONTEXT}
        onApprove={onApprove}
        onReject={vi.fn()}
      />,
    );

    const approve = screen.getByRole("button", {
      name: "Approve identity & start search",
    });
    expect(approve).toBeDisabled();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /verified the resolved identity/i,
      }),
    );
    expect(approve).toBeEnabled();

    fireEvent.click(approve);
    expect(onApprove).toHaveBeenCalledTimes(1);
  });

  it("fails closed when no authoritative source record is bound", () => {
    const onReject = vi.fn();
    const context = {
      ...IDENTITY_CONTEXT,
      resolved_identity: {
        ...(IDENTITY_CONTEXT.resolved_identity as Record<string, unknown>),
        authoritative_record_present: false,
        source_authority: "Name-based biologic classification",
        source_record_id: "",
      },
    };

    render(
      <IdentityReviewCheckpoint
        data={context}
        onApprove={vi.fn()}
        onReject={onReject}
      />,
    );

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /verified the resolved identity/i,
      }),
    );
    expect(
      screen.getByRole("button", {
        name: "Approve identity & start search",
      }),
    ).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Approval is unavailable",
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Reject identity & stop" }),
    );
    expect(onReject).toHaveBeenCalledTimes(1);
  });
});
