"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED, EXPORT_POLL_INTERVAL_MS } from "@/lib/constants";
import { authScopedQueryKey } from "@/lib/query-keys";
import {
  getExportArtifactLabel,
  type ExportAudience,
  type ExportFormat,
  type ExportSection,
} from "@/components/collaboration/export-dialog-constants";
import {
  buildDemoExportDescriptor,
  createDemoExportArtifact,
  createDemoReportPayload,
  sha256Hex,
} from "@/lib/demo-export-artifact";

interface ExportJob {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  download_url?: string;
  format: string;
  file_size_bytes?: number;
  manifest_schema_version?: string | null;
  manifest_hash?: string | null;
  manifest_snapshot?: Record<string, unknown> | null;
  artifact_sha256?: string | null;
  report_payload_sha256?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  retryable?: boolean;
  retry_after_seconds?: number | null;
}

const demoExportJobs = new Map<string, ExportJob>();

async function buildDemoExportJob(
  reportId: string,
  format: ExportFormat,
  audience: ExportAudience = "full",
): Promise<ExportJob> {
  const demoFormat = format;
  const artifact = createDemoExportArtifact(audience, demoFormat);
  const artifactSha256 = await sha256Hex(artifact.bytes);
  const reportPayloadSha256 = await sha256Hex(
    createDemoReportPayload(audience),
  );
  const manifestSnapshot = {
    artifact: {
      file_size_bytes: artifact.bytes.length,
      format,
      report_id: reportId,
      sections: ["executive_summary", "patent_analysis", "audit_trail"],
      synthetic_demo: true,
      title: getExportArtifactLabel(audience, demoFormat),
    },
    readiness: {
      export_ready: true,
      review_status: "approved",
    },
    source_health: {
      healthy_count: 4,
      total_count: 4,
    },
  };
  const manifestHash = await sha256Hex(
    new TextEncoder().encode(JSON.stringify(manifestSnapshot)),
  );
  const jobId = `demo-export-${Math.random().toString(36).slice(2, 10)}`;
  const job: ExportJob = {
    job_id: jobId,
    status: "completed",
    format,
    download_url: buildDemoExportDescriptor(audience, demoFormat),
    file_size_bytes: artifact.bytes.length,
    manifest_schema_version: "export-manifest-v1",
    manifest_hash: manifestHash,
    manifest_snapshot: manifestSnapshot,
    artifact_sha256: artifactSha256,
    report_payload_sha256: reportPayloadSha256,
    completed_at: new Date().toISOString(),
  };
  demoExportJobs.set(jobId, job);
  return job;
}

export function useExportReport(token: string | null) {
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: (data: {
      report_id: string;
      format: ExportFormat;
      sections?: ExportSection[];
      audience?: ExportAudience;
    }) => {
      if (DEMO_MODE_ENABLED) {
        return buildDemoExportJob(data.report_id, data.format, data.audience);
      }
      return apiClient<ExportJob>(`/reports/${data.report_id}/export`, {
        method: "POST",
        body: JSON.stringify({
          format: data.format,
          sections: data.sections,
          audience: data.audience,
        }),
        token: token || undefined,
      });
    },
  });
}

const MAX_RETRYABLE_POLLS = 30;

export function useExportStatus(jobId: string | null, token: string | null) {
  const query = useQuery({
    queryKey: authScopedQueryKey(["export-jobs", jobId] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        const cached = jobId ? demoExportJobs.get(jobId) : undefined;
        if (cached) return Promise.resolve(cached);
        return Promise.reject(new Error(`Demo export job not found: ${jobId}`));
      }
      return apiClient<ExportJob>(`/exports/${jobId}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled: (DEMO_MODE_ENABLED || !!token) && !!jobId,
    // Export job status is polled and rendered inline by the export dialog;
    // a transient poll failure should not raise a separate global error toast.
    meta: { suppressGlobalErrorToast: true },
    refetchInterval: (q) => {
      const data = q.state.data;
      if (data?.status === "pending" || data?.status === "processing") {
        return EXPORT_POLL_INTERVAL_MS;
      }
      // Use the ref so the closure always sees the current retryable-only count,
      // not the lifetime dataUpdateCount which includes non-retryable processing
      // polls and would cap polling prematurely when the job was slow to fail.
      if (data?.status === "failed" && data.retryable) {
        if (retryablePollCountRef.current < MAX_RETRYABLE_POLLS) {
          return EXPORT_POLL_INTERVAL_MS;
        }
      }
      return false;
    },
  });

  // Track retryable-only polls via a ref (visible inside the refetchInterval
  // closure) and mirror to state so isPollingCapped re-renders on change.
  const retryablePollCountRef = useRef(0);
  const [retryablePollCount, setRetryablePollCount] = useState(0);
  useEffect(() => {
    if (query.data?.retryable) {
      retryablePollCountRef.current += 1;
      setRetryablePollCount(retryablePollCountRef.current);
    } else {
      retryablePollCountRef.current = 0;
      setRetryablePollCount(0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.dataUpdatedAt]);

  const isPollingCapped =
    Boolean(query.data?.retryable) && retryablePollCount >= MAX_RETRYABLE_POLLS;

  return { ...query, isPollingCapped };
}
