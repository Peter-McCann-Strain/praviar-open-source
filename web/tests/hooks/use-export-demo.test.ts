import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockApiClient = vi.hoisted(() => vi.fn());

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: true,
  EXPORT_POLL_INTERVAL_MS: 2000,
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: mockApiClient,
}));

import { useExportReport, useExportStatus } from "@/hooks/use-export";
import {
  createDemoExportArtifact,
  createDemoReportPayload,
  sha256Hex,
} from "@/lib/demo-export-artifact";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

describe("export hooks in demo mode", () => {
  beforeEach(() => {
    mockApiClient.mockClear();
  });

  it("creates and resolves export jobs locally", async () => {
    const wrapper = createWrapper();
    const { result, rerender } = renderHook(
      ({ jobId }: { jobId: string | null }) => ({
        exportReport: useExportReport(null),
        exportStatus: useExportStatus(jobId, null),
      }),
      { wrapper, initialProps: { jobId: null } },
    );

    let jobId: string | null = null;
    await act(async () => {
      const job = await result.current.exportReport.mutateAsync({
        report_id: "ana_demo_001",
        format: "pdf",
        sections: ["executive_summary"],
        audience: "attorney",
      });
      jobId = job.job_id;
      expect(job.status).toBe("completed");
      expect(job.download_url).toBe("praviar-demo-export:v1:attorney:pdf");
      expect(job.file_size_bytes).toBeGreaterThan(500);
      expect(job.artifact_sha256).toMatch(/^[0-9a-f]{64}$/u);
      expect(job.manifest_hash).toMatch(/^[0-9a-f]{64}$/u);
      expect(job.report_payload_sha256).toMatch(/^[0-9a-f]{64}$/u);
      expect(job.manifest_snapshot).toMatchObject({
        artifact: {
          file_size_bytes: job.file_size_bytes,
          format: "pdf",
          report_id: "ana_demo_001",
          synthetic_demo: true,
        },
      });
      expect(job.artifact_sha256).toBe(
        await sha256Hex(createDemoExportArtifact("attorney", "pdf").bytes),
      );
      expect(job.report_payload_sha256).toBe(
        await sha256Hex(createDemoReportPayload("attorney")),
      );
      expect(job.manifest_hash).toBe(
        await sha256Hex(
          new TextEncoder().encode(JSON.stringify(job.manifest_snapshot)),
        ),
      );
    });

    rerender({ jobId });
    await waitFor(() =>
      expect(result.current.exportStatus.isSuccess).toBe(true),
    );

    expect(result.current.exportStatus.data?.status).toBe("completed");
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
