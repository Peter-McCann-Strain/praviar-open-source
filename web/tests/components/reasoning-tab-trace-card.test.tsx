import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReasoningTrace } from "@praviar/shared-types";
import { ReasoningTraceCard } from "@/components/report/reasoning-tab-trace-card";

const trace: ReasoningTrace = {
  patent_id: "US0000000001A1",
  model: "claude-3-opus",
  agent_type: "claim_analyst",
  confidence: 0.82,
  self_critique: "Review claim breadth before final sign-off.",
  revisions_made: ["Narrowed the claim overlap assessment."],
  final_output_summary: "Likely blocking claim overlap remains.",
  rounds: [
    {
      round_number: 1,
      thinking_summary: "Compared independent claim 1 to the product route.",
      tool_calls: [],
      observations: "The core process limitation overlaps.",
      scratchpad_delta: {},
      decision: "Escalate for reviewer confirmation",
    },
  ],
  total_input_tokens: 1200,
  total_output_tokens: 300,
  total_duration_ms: 2300,
};

describe("ReasoningTraceCard", () => {
  it("uses a native disclosure button with expanded state", () => {
    render(<ReasoningTraceCard trace={trace} />);

    const expandButton = screen.getByRole("button", {
      name: "Expand claim analyst decision note for US0000000001A1",
    });

    expect(expandButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(expandButton);

    const collapseButton = screen.getByRole("button", {
      name: "Collapse claim analyst decision note for US0000000001A1",
    });
    expect(collapseButton).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("region", {
        name: "claim analyst decision-note details for US0000000001A1",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Review claim breadth before final sign-off."),
    ).toBeInTheDocument();
  });

  it("keeps long patent, model, decision, and tool labels mobile-safe", () => {
    const longDecision =
      "Escalate because this long decision label should not stretch the mobile trace row";
    const longToolName =
      "patent_claim_chart_search_with_long_provider_and_dataset_name";
    const longTrace: ReasoningTrace = {
      ...trace,
      patent_id: "US123456789012345678901234567890B2",
      model: "frontier-claim-verifier-model-with-long-release-channel-name",
      rounds: [
        {
          round_number: 1,
          thinking_summary: "Checked a long model output.",
          tool_calls: [
            {
              tool_name: longToolName,
              duration_ms: 1200,
              tool_output_summary:
                "A long summary that should be clipped instead of stretching the reasoning card header beyond the viewport.",
            },
          ],
          observations: "Observed overlap",
          scratchpad_delta: {},
          decision: longDecision,
        },
      ],
    };

    render(<ReasoningTraceCard trace={longTrace} />);

    const patentId = screen.getByText(longTrace.patent_id);
    expect(patentId).toHaveClass("break-all", "sm:truncate");
    expect(patentId).toHaveAttribute("title", longTrace.patent_id);

    const modelName = screen.getByText(longTrace.model);
    expect(modelName).toHaveClass("truncate");

    fireEvent.click(
      screen.getByRole("button", {
        name: `Expand claim analyst decision note for ${longTrace.patent_id}`,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /round 1/i }));

    const decision = screen.getByText(longDecision);
    expect(decision).toHaveClass("break-words", "sm:truncate");
    expect(decision).toHaveAttribute("title", longDecision);

    const toolName = screen.getByText(longToolName);
    expect(toolName).toHaveClass("break-all", "sm:truncate");
    expect(toolName).toHaveAttribute("title", longToolName);
  });

  it("redacts diagnostics from customer-visible trace summaries", () => {
    const secretTrace: ReasoningTrace = {
      ...trace,
      self_critique: "Review saw postgres://secret-host/praviar",
      revisions_made: ["Revision used sk_live_secret before approval."],
      final_output_summary: "Final summary includes Bearer abc123.",
      rounds: [
        {
          round_number: 1,
          thinking_summary:
            "Reasoning saw SELECT * FROM private_table Traceback provider stack",
          tool_calls: [
            {
              tool_name: "patent_search",
              duration_ms: 900,
              tool_output_summary:
                "Tool returned /Users/example-user/private and sk-proj-abcdefghijklmnop",
            },
          ],
          observations: "Observed password=hunter2 in provider payload.",
          scratchpad_delta: {},
          decision: "Escalate after postgres://decision-secret",
        },
      ],
    };

    render(<ReasoningTraceCard trace={secretTrace} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Expand claim analyst decision note for US0000000001A1",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /round 1/i }));

    expect(
      screen.queryByText(/postgres:\/\/secret-host/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/postgres:\/\/decision-secret/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/sk_live_secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Bearer abc123/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/SELECT \* FROM private_table/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/\/Users\/peter\/private/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/sk-proj-/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hunter2/i)).not.toBeInTheDocument();
    expect(
      screen.getAllByText(/\[redacted connection string\]/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText(/\[redacted API key\]/i).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText(/Bearer \[redacted\]/i)).toBeInTheDocument();
    expect(screen.getByText(/\[redacted query\]/i)).toBeInTheDocument();
    expect(screen.getByText(/\[redacted path\]/i)).toBeInTheDocument();
    expect(screen.getByText(/password=\[redacted\]/i)).toBeInTheDocument();
  });
});
