/**
 * Returns the wall clock used by the fictional share-verification flow.
 *
 * Demo mode is intentionally ordinary runtime behaviour: it does not bind
 * screenshots, evidence, or publication records to a special clock.
 */
export function resolveDemoShareVerificationClock(): Date {
  return new Date();
}
