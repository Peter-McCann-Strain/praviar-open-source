export type VisualMatrixActivitySnapshot = {
  activityVersion: number;
  pendingCount: number;
};

type QuietWindowOptions = {
  label: string;
  pollIntervalMs?: number;
  quietWindowMs?: number;
  timeoutMs?: number;
  now?: () => number;
  sleep?: (durationMs: number) => Promise<void>;
};

/**
 * Requires a continuous period with no pending work and no observed activity.
 * A request or diagnostic that starts after an initial zero resets the clock,
 * closing the late-event gap left by a one-shot pending-request poll.
 */
export async function waitForVisualMatrixQuietWindow(
  readSnapshot: () => VisualMatrixActivitySnapshot,
  {
    label,
    now = () => Date.now(),
    pollIntervalMs = 25,
    quietWindowMs = 200,
    sleep = (durationMs) =>
      new Promise((resolve) => setTimeout(resolve, durationMs)),
    timeoutMs = 20_000,
  }: QuietWindowOptions,
): Promise<void> {
  if (pollIntervalMs <= 0 || quietWindowMs < 0 || timeoutMs <= 0) {
    throw new Error("Visual matrix quiet-window durations must be positive");
  }

  const startedAt = now();
  let quietStartedAt: number | null = null;
  let quietVersion: number | null = null;
  let lastSnapshot = readSnapshot();

  while (now() - startedAt <= timeoutMs) {
    const observedAt = now();
    lastSnapshot = readSnapshot();
    if (lastSnapshot.pendingCount === 0) {
      if (
        quietStartedAt === null ||
        quietVersion !== lastSnapshot.activityVersion
      ) {
        quietStartedAt = observedAt;
        quietVersion = lastSnapshot.activityVersion;
      } else if (observedAt - quietStartedAt >= quietWindowMs) {
        return;
      }
    } else {
      quietStartedAt = null;
      quietVersion = null;
    }
    await sleep(pollIntervalMs);
  }

  throw new Error(
    `${label} did not reach a ${quietWindowMs}ms quiet window within ${timeoutMs}ms ` +
      `(pending=${lastSnapshot.pendingCount}, activityVersion=${lastSnapshot.activityVersion})`,
  );
}
