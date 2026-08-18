export const DIGEST_UNSUBSCRIBE_COOKIE = "praviar_digest_unsubscribe";
export const DIGEST_UNSUBSCRIBE_TOKEN_MIN_LENGTH = 80;
export const DIGEST_UNSUBSCRIBE_TOKEN_MAX_LENGTH = 2048;

export function hasUsableDigestUnsubscribeToken(token: string): boolean {
  return (
    token.length >= DIGEST_UNSUBSCRIBE_TOKEN_MIN_LENGTH &&
    token.length <= DIGEST_UNSUBSCRIBE_TOKEN_MAX_LENGTH
  );
}
