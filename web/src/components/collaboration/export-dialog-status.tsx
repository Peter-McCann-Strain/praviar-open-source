"use client";

import { type RefObject, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  Copy,
  Download,
  FileCheck2,
  type LucideIcon,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { PdfViewer } from "@/components/report/pdf-viewer";
import { copyTextToClipboard } from "@/components/report/share-analytics-helpers";
import { API_BASE_URL, DEMO_MODE_ENABLED } from "@/lib/constants";
import { createDemoExportArtifact } from "@/lib/demo-export-artifact";
import { logError } from "@/lib/error-logger";
import {
  classifyExportDownloadUrl,
  type ExportDownloadTarget,
} from "@/lib/export-download-url";
import { cn } from "@/lib/utils";
import type { ExportFormat } from "./export-dialog-constants";

type ExportManifestSnapshot = Record<string, unknown>;

interface ExportDialogStatusProps {
  isCompleted: boolean;
  isFailed?: boolean;
  isRetryableFailure?: boolean;
  isPollingCapped?: boolean;
  selectedFormat: ExportFormat;
  verifiedClaimChartPacketActive?: boolean;
  downloadUrl?: string | null;
  retryAfterSeconds?: number | null;
  manifestHash?: string | null;
  manifestSnapshot?: ExportManifestSnapshot | null;
  manifestSchemaVersion?: string | null;
  artifactSha256?: string | null;
  reportPayloadSha256?: string | null;
  fileSizeBytes?: number | null;
  artifactLabel?: string | null;
  completedAt?: string | null;
  token?: string | null;
}

interface PreparedDownload {
  fileName: string;
  sizeBytes: number;
  sourceKey: string;
  url: string;
}

interface DownloadPrepError {
  message: string;
  sourceKey: string;
}

interface DownloadPreparationInput {
  artifactLabel?: string | null;
  artifactSha256?: string | null;
  downloadUrl?: string | null;
  fileSizeBytes?: number | null;
  isCompleted: boolean;
  selectedFormat: ExportFormat;
  token?: string | null;
}

interface PreparedExportDownload {
  downloadHref: string | null;
  downloadLinkRef: RefObject<HTMLAnchorElement | null>;
  downloadPrepError: string | null;
  downloadSafetyError: string | null;
  fileName?: string;
  sizeBytes?: number;
}

interface ReadyStatusModel {
  artifactSha256?: string | null;
  completedAt?: string | null;
  downloadHref: string;
  downloadLabel: string;
  fileName?: string;
  manifestHash?: string | null;
  manifestSchemaVersion?: string | null;
  receiptModel: ReceiptModel;
  reportPayloadSha256?: string | null;
  selectedFormat: ExportFormat;
}

type ExportStatusViewModel =
  | { kind: "polling-capped" }
  | { kind: "retrying"; retryCopy: string }
  | { kind: "failed" }
  | { kind: "hidden" }
  | { kind: "missing-download" }
  | { kind: "error"; message: string }
  | { kind: "preparing" }
  | ({ kind: "ready" } & ReadyStatusModel);

export function ExportDialogStatus({
  isCompleted,
  isFailed = false,
  isRetryableFailure = false,
  isPollingCapped = false,
  selectedFormat,
  verifiedClaimChartPacketActive = false,
  downloadUrl,
  retryAfterSeconds,
  manifestHash,
  manifestSnapshot,
  manifestSchemaVersion,
  artifactSha256,
  reportPayloadSha256,
  fileSizeBytes,
  artifactLabel,
  completedAt,
  token,
}: ExportDialogStatusProps) {
  const preparedDownload = usePreparedExportDownload({
    artifactLabel,
    artifactSha256,
    downloadUrl,
    fileSizeBytes,
    isCompleted,
    selectedFormat,
    token,
  });
  const viewModel = buildExportStatusViewModel({
    artifactLabel,
    artifactSha256,
    completedAt,
    downloadHref: preparedDownload.downloadHref,
    downloadPrepError: preparedDownload.downloadPrepError,
    downloadSafetyError: preparedDownload.downloadSafetyError,
    fileName: preparedDownload.fileName,
    fileSizeBytes: preparedDownload.sizeBytes ?? fileSizeBytes,
    isCompleted,
    isFailed,
    isPollingCapped,
    isRetryableFailure,
    manifestHash,
    manifestSchemaVersion,
    manifestSnapshot,
    reportPayloadSha256,
    retryAfterSeconds,
    selectedFormat,
    verifiedClaimChartPacketActive,
    downloadUrl,
  });

  return (
    <ExportDialogStatusView
      downloadLinkRef={preparedDownload.downloadLinkRef}
      viewModel={viewModel}
    />
  );
}

function usePreparedExportDownload({
  artifactLabel,
  artifactSha256,
  downloadUrl,
  fileSizeBytes,
  isCompleted,
  selectedFormat,
  token,
}: DownloadPreparationInput): PreparedExportDownload {
  const downloadLinkRef = useRef<HTMLAnchorElement | null>(null);
  const [preparedDownload, setPreparedDownload] =
    useState<PreparedDownload | null>(null);
  const [downloadPrepError, setDownloadPrepError] =
    useState<DownloadPrepError | null>(null);
  const downloadTarget = getDownloadTarget(downloadUrl);
  const preparationKey = buildPreparationKey({
    artifactLabel,
    artifactSha256,
    downloadUrl,
    selectedFormat,
  });
  const objectUrlAvailable = canPrepareObjectUrl();
  const preparationPlan = buildDownloadPreparationPlan({
    downloadTarget,
    isCompleted,
    objectUrlAvailable,
    selectedFormat,
    token,
  });

  useAuthenticatedDownloadPreparation({
    artifactLabel,
    fileSizeBytes,
    preparationKey,
    protectedDownloadPath: preparationPlan.protectedDownloadPath,
    selectedFormat,
    setDownloadPrepError,
    setPreparedDownload,
    shouldPrepare: preparationPlan.shouldPrepareAuthenticatedDownload,
    token,
  });
  useDemoDownloadPreparation({
    audience: preparationPlan.demoDownloadAudience,
    format: preparationPlan.demoDownloadFormat,
    preparationKey,
    setDownloadPrepError,
    setPreparedDownload,
    shouldPrepare: preparationPlan.shouldPrepareDemoDownload,
  });

  const currentDownload = getCurrentPreparedDownload(
    preparedDownload,
    preparationKey,
  );
  const currentPrepError = getCurrentDownloadPrepError(
    downloadPrepError,
    preparationKey,
  );
  const downloadSafetyError = getDownloadSafetyError({
    downloadTarget,
    objectUrlAvailable,
    selectedFormat,
    token,
  });

  useDownloadFocus(downloadLinkRef, currentDownload?.url ?? null, isCompleted);

  return {
    downloadHref: currentDownload?.url ?? null,
    downloadLinkRef,
    downloadPrepError: currentPrepError,
    downloadSafetyError,
    fileName: currentDownload?.fileName,
    sizeBytes: currentDownload?.sizeBytes,
  };
}

interface AuthenticatedDownloadPreparationInput {
  artifactLabel?: string | null;
  fileSizeBytes?: number | null;
  preparationKey: string;
  protectedDownloadPath: string | null;
  selectedFormat: ExportFormat;
  setDownloadPrepError: (error: DownloadPrepError) => void;
  setPreparedDownload: (download: PreparedDownload) => void;
  shouldPrepare: boolean;
  token?: string | null;
}

function useAuthenticatedDownloadPreparation({
  artifactLabel,
  fileSizeBytes,
  preparationKey,
  protectedDownloadPath,
  selectedFormat,
  setDownloadPrepError,
  setPreparedDownload,
  shouldPrepare,
  token,
}: AuthenticatedDownloadPreparationInput) {
  useEffect(() => {
    if (!shouldPrepare || !token || !protectedDownloadPath) {
      return;
    }

    const controller = new AbortController();
    let objectUrl: string | null = null;
    let disposed = false;
    const sourceKey = preparationKey;
    const authorizedDownloadPath = protectedDownloadPath;

    async function prepareDownload() {
      try {
        const response = await fetch(
          resolveProtectedDownloadUrl(authorizedDownloadPath),
          {
            headers: {
              Accept: "application/octet-stream,application/pdf,*/*",
              Authorization: `Bearer ${token}`,
            },
            signal: controller.signal,
          },
        );
        if (!response.ok) {
          throw new Error(`Download request failed with ${response.status}`);
        }
        const blob = await response.blob();
        if (disposed || controller.signal.aborted) return;
        const browserSafeBlob =
          selectedFormat === "pdf" ? await preparePdfPreviewBlob(blob) : blob;
        if (disposed || controller.signal.aborted) return;
        validatePreparedBlob(browserSafeBlob, fileSizeBytes);
        const nextObjectUrl = URL.createObjectURL(browserSafeBlob);
        if (disposed || controller.signal.aborted) {
          URL.revokeObjectURL(nextObjectUrl);
          return;
        }
        objectUrl = nextObjectUrl;
        setPreparedDownload({
          fileName: buildDownloadFileName(artifactLabel, selectedFormat),
          sizeBytes: browserSafeBlob.size,
          sourceKey,
          url: objectUrl,
        });
      } catch (error) {
        if (disposed || controller.signal.aborted) return;
        logError(error, {
          source: "ExportDialogStatus",
          extra: { action: "prepare_secure_download" },
        });
        setDownloadPrepError({
          message:
            "Export is ready, but the secure download could not be prepared.",
          sourceKey,
        });
      }
    }

    void prepareDownload();

    return () => {
      disposed = true;
      controller.abort();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [
    artifactLabel,
    fileSizeBytes,
    preparationKey,
    protectedDownloadPath,
    selectedFormat,
    setDownloadPrepError,
    setPreparedDownload,
    shouldPrepare,
    token,
  ]);
}

interface DemoDownloadPreparationInput {
  audience: Parameters<typeof createDemoExportArtifact>[0] | null;
  format: Parameters<typeof createDemoExportArtifact>[1] | null;
  preparationKey: string;
  setDownloadPrepError: (error: DownloadPrepError) => void;
  setPreparedDownload: (download: PreparedDownload) => void;
  shouldPrepare: boolean;
}

function useDemoDownloadPreparation({
  audience,
  format,
  preparationKey,
  setDownloadPrepError,
  setPreparedDownload,
  shouldPrepare,
}: DemoDownloadPreparationInput) {
  useEffect(() => {
    if (!shouldPrepare || !audience || !format) {
      return;
    }

    const sourceKey = preparationKey;
    const artifactAudience = audience;
    const artifactFormat = format;
    let objectUrl: string | null = null;
    let disposed = false;

    async function prepareDemoDownload() {
      await Promise.resolve();
      if (disposed) return;
      try {
        const artifact = createDemoExportArtifact(
          artifactAudience,
          artifactFormat,
        );
        objectUrl = URL.createObjectURL(
          new Blob([artifact.bytes.slice().buffer], {
            type: artifact.mediaType,
          }),
        );
        setPreparedDownload({
          fileName: artifact.fileName,
          sizeBytes: artifact.bytes.length,
          sourceKey,
          url: objectUrl,
        });
      } catch {
        logError(new Error("Demo export artifact preparation failed"), {
          source: "ExportDialogStatus",
          extra: { action: "prepare_demo_download" },
        });
        setDownloadPrepError({
          message: "The local demonstration export could not be prepared.",
          sourceKey,
        });
      }
    }

    void prepareDemoDownload();

    return () => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [
    audience,
    format,
    preparationKey,
    setDownloadPrepError,
    setPreparedDownload,
    shouldPrepare,
  ]);
}

function useDownloadFocus(
  downloadLinkRef: RefObject<HTMLAnchorElement | null>,
  downloadHref: string | null,
  isCompleted: boolean,
) {
  useEffect(() => {
    if (isCompleted && downloadHref) {
      downloadLinkRef.current?.focus();
    }
  }, [downloadHref, downloadLinkRef, isCompleted]);
}

function getDownloadTarget(
  downloadUrl?: string | null,
): ExportDownloadTarget | null {
  return downloadUrl
    ? classifyExportDownloadUrl(downloadUrl, {
        allowDemoArtifact: DEMO_MODE_ENABLED,
      })
    : null;
}

interface DownloadPreparationPlan {
  demoDownloadAudience: Parameters<typeof createDemoExportArtifact>[0] | null;
  demoDownloadFormat: Parameters<typeof createDemoExportArtifact>[1] | null;
  protectedDownloadPath: string | null;
  shouldPrepareAuthenticatedDownload: boolean;
  shouldPrepareDemoDownload: boolean;
}

function buildDownloadPreparationPlan({
  downloadTarget,
  isCompleted,
  objectUrlAvailable,
  selectedFormat,
  token,
}: {
  downloadTarget: ExportDownloadTarget | null;
  isCompleted: boolean;
  objectUrlAvailable: boolean;
  selectedFormat: ExportFormat;
  token?: string | null;
}): DownloadPreparationPlan {
  const isProtectedDownload = downloadTarget?.kind === "protected-api";
  const isDemoDownload = downloadTarget?.kind === "demo-artifact";
  return {
    demoDownloadAudience: isDemoDownload ? downloadTarget.audience : null,
    demoDownloadFormat: isDemoDownload ? downloadTarget.format : null,
    protectedDownloadPath: isProtectedDownload ? downloadTarget.path : null,
    shouldPrepareAuthenticatedDownload: Boolean(
      isCompleted && isProtectedDownload && token && objectUrlAvailable,
    ),
    shouldPrepareDemoDownload: Boolean(
      isCompleted &&
      isDemoDownload &&
      downloadTarget.format === selectedFormat &&
      objectUrlAvailable,
    ),
  };
}

function buildPreparationKey({
  artifactLabel,
  artifactSha256,
  downloadUrl,
  selectedFormat,
}: Pick<
  DownloadPreparationInput,
  "artifactLabel" | "artifactSha256" | "downloadUrl" | "selectedFormat"
>): string {
  return [downloadUrl, selectedFormat, artifactLabel, artifactSha256].join("|");
}

function getCurrentPreparedDownload(
  preparedDownload: PreparedDownload | null,
  preparationKey: string,
): PreparedDownload | null {
  return preparedDownload?.sourceKey === preparationKey
    ? preparedDownload
    : null;
}

function getCurrentDownloadPrepError(
  downloadPrepError: DownloadPrepError | null,
  preparationKey: string,
): string | null {
  return downloadPrepError?.sourceKey === preparationKey
    ? downloadPrepError.message
    : null;
}

function getDownloadSafetyError({
  downloadTarget,
  objectUrlAvailable,
  selectedFormat,
  token,
}: {
  downloadTarget: ExportDownloadTarget | null;
  objectUrlAvailable: boolean;
  selectedFormat: ExportFormat;
  token?: string | null;
}): string | null {
  if (downloadTarget?.kind === "invalid") {
    return "Export finished, but its download link did not pass security validation.";
  }
  if (
    downloadTarget?.kind === "demo-artifact" &&
    downloadTarget.format !== selectedFormat
  ) {
    return "Export finished, but its artifact format did not pass security validation.";
  }
  if (
    downloadTarget?.kind === "protected-api" &&
    (!token || !objectUrlAvailable)
  ) {
    return "Export is ready, but secure download authorization is unavailable.";
  }
  if (downloadTarget?.kind === "demo-artifact" && !objectUrlAvailable) {
    return "Export is ready, but local demo download preparation is unavailable.";
  }
  return null;
}

function validatePreparedBlob(blob: Blob, expectedSizeBytes?: number | null) {
  if (blob.size <= 0) {
    throw new Error("Export artifact was empty");
  }
  if (
    typeof expectedSizeBytes === "number" &&
    expectedSizeBytes > 0 &&
    blob.size !== expectedSizeBytes
  ) {
    throw new Error("Export artifact size did not match its receipt");
  }
}

interface ExportStatusViewModelInput {
  artifactLabel?: string | null;
  artifactSha256?: string | null;
  completedAt?: string | null;
  downloadHref: string | null;
  downloadPrepError: string | null;
  downloadSafetyError: string | null;
  downloadUrl?: string | null;
  fileName?: string;
  fileSizeBytes?: number | null;
  isCompleted: boolean;
  isFailed: boolean;
  isPollingCapped: boolean;
  isRetryableFailure: boolean;
  manifestHash?: string | null;
  manifestSchemaVersion?: string | null;
  manifestSnapshot?: ExportManifestSnapshot | null;
  reportPayloadSha256?: string | null;
  retryAfterSeconds?: number | null;
  selectedFormat: ExportFormat;
  verifiedClaimChartPacketActive: boolean;
}

function buildExportStatusViewModel({
  artifactLabel,
  artifactSha256,
  completedAt,
  downloadHref,
  downloadPrepError,
  downloadSafetyError,
  downloadUrl,
  fileName,
  fileSizeBytes,
  isCompleted,
  isFailed,
  isPollingCapped,
  isRetryableFailure,
  manifestHash,
  manifestSchemaVersion,
  manifestSnapshot,
  reportPayloadSha256,
  retryAfterSeconds,
  selectedFormat,
  verifiedClaimChartPacketActive,
}: ExportStatusViewModelInput): ExportStatusViewModel {
  if (isPollingCapped) return { kind: "polling-capped" };
  if (isRetryableFailure) {
    return {
      kind: "retrying",
      retryCopy:
        typeof retryAfterSeconds === "number" && retryAfterSeconds > 0
          ? `Retrying in about ${retryAfterSeconds} seconds.`
          : "Retrying shortly.",
    };
  }
  if (isFailed) return { kind: "failed" };
  if (!isCompleted) return { kind: "hidden" };
  if (!downloadUrl) return { kind: "missing-download" };
  if (downloadSafetyError) {
    return { kind: "error", message: downloadSafetyError };
  }
  if (downloadPrepError) {
    return { kind: "error", message: downloadPrepError };
  }
  if (!downloadHref) return { kind: "preparing" };

  const hasVerificationReceipt = Boolean(
    artifactSha256 || manifestHash || reportPayloadSha256,
  );
  return {
    artifactSha256,
    completedAt,
    downloadHref,
    downloadLabel: getDownloadLabel(
      hasVerificationReceipt,
      verifiedClaimChartPacketActive,
    ),
    fileName,
    kind: "ready",
    manifestHash,
    manifestSchemaVersion,
    receiptModel: buildReceiptModel({
      artifactLabel,
      fileSizeBytes,
      manifestSnapshot,
    }),
    reportPayloadSha256,
    selectedFormat,
  };
}

function getDownloadLabel(
  hasVerificationReceipt: boolean,
  verifiedClaimChartPacketActive: boolean,
): string {
  if (!hasVerificationReceipt) return "Export ready — click to download";
  return verifiedClaimChartPacketActive
    ? "Download verified claim-chart DOCX"
    : "Download verified packet";
}

function ExportDialogStatusView({
  downloadLinkRef,
  viewModel,
}: {
  downloadLinkRef: RefObject<HTMLAnchorElement | null>;
  viewModel: ExportStatusViewModel;
}) {
  switch (viewModel.kind) {
    case "polling-capped":
      return <PollingCappedStatus />;
    case "retrying":
      return <RetryingStatus retryCopy={viewModel.retryCopy} />;
    case "failed":
      return <FailedStatus />;
    case "hidden":
      return null;
    case "missing-download":
      return <MissingDownloadStatus />;
    case "error":
      return <DownloadErrorStatus message={viewModel.message} />;
    case "preparing":
      return <PreparingDownloadStatus />;
    case "ready":
      return (
        <ReadyDownloadStatus
          downloadLinkRef={downloadLinkRef}
          model={viewModel}
        />
      );
  }
}

function PollingCappedStatus() {
  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-error/30 bg-error/10 p-3 text-sm text-error"
      role="alert"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>Export is taking longer than expected. Please try again.</span>
    </div>
  );
}

function RetryingStatus({ retryCopy }: { retryCopy: string }) {
  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning"
      role="status"
      aria-live="polite"
    >
      <RefreshCw
        className="mt-0.5 h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none"
        aria-hidden="true"
      />
      <span>Export hit a temporary worker issue. {retryCopy}</span>
    </div>
  );
}

function FailedStatus() {
  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-error/30 bg-error/10 p-3 text-sm text-error"
      role="alert"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>
        Export failed. Please review readiness and try again. If this repeats,
        use the operator-approved support channel for your deployment.
      </span>
    </div>
  );
}

function MissingDownloadStatus() {
  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning"
      role="alert"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>
        Export finished, but no download link was returned. Try again or contact
        support if this repeats.
      </span>
    </div>
  );
}

function DownloadErrorStatus({ message }: { message: string }) {
  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-error/30 bg-error/10 p-3 text-sm text-error"
      role="alert"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

function PreparingDownloadStatus() {
  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-brand-primary/20 bg-brand-primary/8 p-3 text-sm text-brand-primary"
      role="status"
      aria-live="polite"
    >
      <RefreshCw
        className="mt-0.5 h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none"
        aria-hidden="true"
      />
      <span>Preparing secure download...</span>
    </div>
  );
}

function ReadyDownloadStatus({
  downloadLinkRef,
  model,
}: {
  downloadLinkRef: RefObject<HTMLAnchorElement | null>;
  model: ReadyStatusModel;
}) {
  return (
    <>
      <div
        className="rounded-lg border border-success/25 bg-[color-mix(in_srgb,var(--bg-surface)_82%,var(--color-success)_18%)] p-3 shadow-[var(--shadow-sm)]"
        role="status"
        aria-live="polite"
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-success/25 bg-success/10 text-success shadow-[inset_0_1px_0_rgba(246,244,239,0.7)]">
              <CheckCircle className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Evidence packet ready
              </p>
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                {model.receiptModel.artifactTitle}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <ReceiptPill icon={ShieldCheck} label="Receipt sealed" />
                {model.receiptModel.fileSizeLabel ? (
                  <ReceiptPill
                    icon={FileCheck2}
                    label={model.receiptModel.fileSizeLabel}
                  />
                ) : null}
              </div>
            </div>
          </div>
          <a
            ref={downloadLinkRef}
            href={model.downloadHref}
            download={model.fileName}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-md border border-brand-primary/25 bg-brand-primary px-4 py-2 text-sm font-semibold text-white shadow-[0_12px_28px_rgba(0,91,99,0.22)] transition-colors hover:bg-brand-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            {model.downloadLabel}
          </a>
        </div>
      </div>
      <ExportVerificationReceipt
        artifactLabel={model.receiptModel.artifactTitle}
        artifactSha256={model.artifactSha256}
        completedAt={model.completedAt}
        fileSizeLabel={model.receiptModel.fileSizeLabel}
        manifestHash={model.manifestHash}
        manifestSchemaVersion={model.manifestSchemaVersion}
        reportPayloadSha256={model.reportPayloadSha256}
        receiptHighlights={model.receiptModel.highlights}
      />

      {model.selectedFormat === "pdf" ? (
        <div className="h-[300px]">
          <PdfViewer pdfUrl={model.downloadHref} title="Export Preview" />
        </div>
      ) : null}
    </>
  );
}

function ExportVerificationReceipt({
  artifactLabel,
  artifactSha256,
  completedAt,
  fileSizeLabel,
  manifestHash,
  manifestSchemaVersion,
  reportPayloadSha256,
  receiptHighlights,
}: {
  artifactLabel: string;
  artifactSha256?: string | null;
  completedAt?: string | null;
  fileSizeLabel?: string | null;
  manifestHash?: string | null;
  manifestSchemaVersion?: string | null;
  reportPayloadSha256?: string | null;
  receiptHighlights: ReceiptHighlight[];
}) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const copyResetTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(false);
  const hasReceipt = Boolean(
    artifactSha256 || manifestHash || reportPayloadSha256,
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (copyResetTimerRef.current) {
        window.clearTimeout(copyResetTimerRef.current);
      }
    };
  }, []);

  async function copyReceipt() {
    if (typeof navigator === "undefined") return;
    setCopyFailed(false);
    try {
      await copyTextToClipboard(
        buildReceiptCopyText({
          artifactLabel,
          artifactSha256,
          completedAt,
          fileSizeLabel,
          manifestHash,
          manifestSchemaVersion,
          receiptHighlights,
          reportPayloadSha256,
        }),
      );
    } catch {
      if (!mountedRef.current) return;
      setCopied(false);
      setCopyFailed(true);
      return;
    }
    if (!mountedRef.current) return;
    setCopied(true);
    if (copyResetTimerRef.current) {
      window.clearTimeout(copyResetTimerRef.current);
    }
    copyResetTimerRef.current = window.setTimeout(() => {
      setCopied(false);
      copyResetTimerRef.current = null;
    }, 1800);
  }

  const copyStatus = copyFailed
    ? "Receipt could not be copied. Select the hashes manually."
    : copied
      ? "Verification receipt copied."
      : null;

  if (!hasReceipt) {
    return (
      <section
        aria-label="Export verification receipt"
        className="rounded-lg border border-warning/25 bg-warning/10 p-3 text-sm text-[var(--text-primary)]"
      >
        <p className="font-semibold text-warning">Receipt unavailable</p>
        <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
          This completed export predates durable verification receipts.
        </p>
      </section>
    );
  }

  return (
    <section
      aria-label="Export verification receipt"
      className="rounded-lg border border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_88%,var(--brand-soft-mint)_12%)] p-3 text-sm text-[var(--text-primary)] shadow-[var(--shadow-xs)]"
    >
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="font-semibold text-[var(--text-primary)]">
            Verification receipt
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            Use this receipt to confirm the downloaded file, manifest, and
            report payload match the export generated by Praviar.
          </p>
        </div>
        <button
          type="button"
          onClick={copyReceipt}
          className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/10 px-3 text-xs font-semibold text-brand-primary hover:bg-brand-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
        >
          <Copy className="h-3.5 w-3.5" aria-hidden="true" />
          {copied ? "Receipt copied" : "Copy receipt"}
        </button>
      </div>
      {copyStatus && (
        <p
          className={cn(
            "mt-2 text-xs",
            copyFailed ? "text-destructive" : "text-success",
          )}
          role="status"
          aria-live="polite"
        >
          {copyStatus}
        </p>
      )}
      {receiptHighlights.length > 0 ? (
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          {receiptHighlights.map((item) => (
            <ReceiptSummaryDatum
              key={item.label}
              label={item.label}
              tone={item.tone}
              value={item.value}
            />
          ))}
        </dl>
      ) : null}
      <dl className="mt-3 grid gap-2">
        <ReceiptDatum label="Artifact SHA-256" value={artifactSha256} />
        <ReceiptDatum label="Manifest SHA-256" value={manifestHash} />
        <ReceiptDatum
          label="Report payload SHA-256"
          value={reportPayloadSha256}
        />
        <ReceiptDatum
          label="Receipt schema"
          value={manifestSchemaVersion ?? undefined}
        />
        <ReceiptDatum label="Completed" value={completedAt ?? undefined} />
      </dl>
      <p className="mt-3 rounded-md border border-warning/25 bg-warning/10 px-2.5 py-2 text-xs leading-5 text-[var(--text-secondary)]">
        AI-assisted screening; counsel review required before reliance. This
        receipt verifies file identity and export scope, not legal clearance.
      </p>
    </section>
  );
}

interface ReceiptHighlight {
  label: string;
  tone?: "success" | "warning";
  value: string;
}

interface ReceiptModel {
  artifactTitle: string;
  fileSizeLabel: string | null;
  highlights: ReceiptHighlight[];
}

function ReceiptSummaryDatum({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: ReceiptHighlight["tone"];
  value: string;
}) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-md border px-2.5 py-2",
        tone === "success"
          ? "border-success/25 bg-success/10"
          : tone === "warning"
            ? "border-warning/25 bg-warning/10"
            : "border-[var(--border-subtle)] bg-[var(--bg-surface)]/78",
      )}
    >
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 truncate text-xs font-semibold text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}

function ReceiptDatum({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  if (!value) return null;
  return (
    <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 px-2.5 py-2">
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 break-all font-mono text-xs leading-5 text-[var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}

function ReceiptPill({
  icon: Icon,
  label,
}: {
  icon: LucideIcon;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-success/20 bg-success/10 px-2 py-1 text-xs font-semibold text-success-emphasis">
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label}
    </span>
  );
}

function buildReceiptModel({
  artifactLabel,
  fileSizeBytes,
  manifestSnapshot,
}: {
  artifactLabel?: string | null;
  fileSizeBytes?: number | null;
  manifestSnapshot?: ExportManifestSnapshot | null;
}): ReceiptModel {
  const artifact = asRecord(manifestSnapshot?.artifact);
  const readiness = asRecord(manifestSnapshot?.readiness);
  const review = asRecord(manifestSnapshot?.review);
  const sourceHealth = asRecord(manifestSnapshot?.source_health);
  const artifactTitle =
    stringValue(artifact?.title) ||
    artifactLabel ||
    stringValue(artifact?.format_label) ||
    "Verified export packet";
  const sections = arrayValue(artifact?.sections);
  const sourceHealthyCount = numberValue(sourceHealth?.healthy_count);
  const sourceTotalCount = numberValue(sourceHealth?.total_count);
  const exportReady = readiness?.export_ready;
  const reviewStatus = stringValue(readiness?.review_status);
  const reviewCompletionPct = numberValue(review?.completion_pct);
  const resolvedFileSize =
    numberValue(artifact?.file_size_bytes) ?? fileSizeBytes ?? undefined;
  const highlights = compactReceiptHighlights([
    buildScopeHighlight(sections),
    buildSourceHealthHighlight(sourceHealthyCount, sourceTotalCount),
    buildReviewHighlight(reviewStatus, reviewCompletionPct),
    buildBackendGateHighlight(exportReady),
  ]);

  return {
    artifactTitle,
    fileSizeLabel: formatFileSize(resolvedFileSize),
    highlights,
  };
}

function compactReceiptHighlights(
  highlights: Array<ReceiptHighlight | null>,
): ReceiptHighlight[] {
  return highlights.filter(
    (highlight): highlight is ReceiptHighlight => highlight !== null,
  );
}

function buildScopeHighlight(sections: string[]): ReceiptHighlight | null {
  if (sections.length === 0) return null;
  return {
    label: "Scope",
    value: `${sections.length.toLocaleString()} section${
      sections.length === 1 ? "" : "s"
    } sealed`,
  };
}

function buildSourceHealthHighlight(
  healthyCount?: number,
  totalCount?: number,
): ReceiptHighlight | null {
  if (
    typeof healthyCount !== "number" ||
    typeof totalCount !== "number" ||
    totalCount <= 0
  ) {
    return null;
  }
  return {
    label: "Source health",
    tone: healthyCount === totalCount ? "success" : "warning",
    value: `${healthyCount.toLocaleString()} / ${totalCount.toLocaleString()} sources healthy`,
  };
}

function buildReviewHighlight(
  reviewStatus?: string,
  reviewCompletionPct?: number,
): ReceiptHighlight | null {
  if (reviewStatus) {
    const approved = reviewStatus === "approved";
    return {
      label: "Review posture",
      tone: approved ? "success" : "warning",
      value: approved ? "Counsel review recorded" : humanizeToken(reviewStatus),
    };
  }
  if (typeof reviewCompletionPct !== "number") return null;
  return {
    label: "Review posture",
    tone: reviewCompletionPct >= 100 ? "success" : "warning",
    value: `${Math.round(reviewCompletionPct).toLocaleString()}% reviewed`,
  };
}

function buildBackendGateHighlight(
  exportReady: unknown,
): ReceiptHighlight | null {
  if (typeof exportReady !== "boolean") return null;
  return {
    label: "Backend gate",
    tone: exportReady ? "success" : "warning",
    value: exportReady ? "Export ready" : "Export caveats preserved",
  };
}

function buildReceiptCopyText({
  artifactLabel,
  artifactSha256,
  completedAt,
  fileSizeLabel,
  manifestHash,
  manifestSchemaVersion,
  receiptHighlights,
  reportPayloadSha256,
}: {
  artifactLabel: string;
  artifactSha256?: string | null;
  completedAt?: string | null;
  fileSizeLabel?: string | null;
  manifestHash?: string | null;
  manifestSchemaVersion?: string | null;
  receiptHighlights: ReceiptHighlight[];
  reportPayloadSha256?: string | null;
}) {
  const lines = [
    "Praviar export verification receipt",
    `Artifact: ${artifactLabel}`,
    fileSizeLabel ? `File size: ${fileSizeLabel}` : null,
    completedAt ? `Completed: ${completedAt}` : null,
    manifestSchemaVersion ? `Receipt schema: ${manifestSchemaVersion}` : null,
    ...receiptHighlights.map((item) => `${item.label}: ${item.value}`),
    artifactSha256 ? `Artifact SHA-256: ${artifactSha256}` : null,
    manifestHash ? `Manifest SHA-256: ${manifestHash}` : null,
    reportPayloadSha256
      ? `Report payload SHA-256: ${reportPayloadSha256}`
      : null,
    "Guardrail: AI-assisted screening; counsel review required before reliance.",
  ];
  return lines.filter(Boolean).join("\n");
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function arrayValue(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item === "string" && item.trim()) return [item.trim()];
    return [];
  });
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function humanizeToken(value: string) {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatFileSize(bytes?: number | null): string | null {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes <= 0) {
    return null;
  }
  if (bytes < 1024) {
    return `${Math.round(bytes).toLocaleString("en-US")} B`;
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: bytes >= 1024 * 1024 ? 1 : 0,
    minimumFractionDigits: bytes >= 1024 * 1024 ? 1 : 0,
    style: "unit",
    unit: bytes >= 1024 * 1024 ? "megabyte" : "kilobyte",
    unitDisplay: "short",
  }).format(bytes >= 1024 * 1024 ? bytes / (1024 * 1024) : bytes / 1024);
}

function canPrepareObjectUrl() {
  return (
    typeof fetch === "function" &&
    typeof URL !== "undefined" &&
    typeof URL.createObjectURL === "function"
  );
}

function resolveProtectedDownloadUrl(url: string) {
  if (!API_BASE_URL) {
    return url;
  }
  return `${API_BASE_URL}${url}`;
}

function buildDownloadFileName(
  artifactLabel: string | null | undefined,
  format: ExportFormat,
): string {
  const stem = (artifactLabel ?? "praviar-export")
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "-")
    .replace(/^-+|-+$/gu, "")
    .slice(0, 80);
  return `${stem || "praviar-export"}.${format}`;
}

async function preparePdfPreviewBlob(blob: Blob): Promise<Blob> {
  const header = await blob.slice(0, 1024).text();
  if (!header.includes("%PDF-")) {
    throw new Error("Export response was not a PDF document");
  }

  // A blob URL inherits the creating page's origin. Force PDF interpretation
  // before embedding it so a mislabelled HTML response can never become a
  // same-origin script document inside PdfViewer's iframe.
  return blob.slice(0, blob.size, "application/pdf");
}
