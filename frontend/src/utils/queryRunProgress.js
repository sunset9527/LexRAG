/** Return a stable, user-facing elapsed-time label for an active query run. */
export function formatElapsedSeconds(startedAt, now = Date.now()) {
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000))
  return `${seconds} 秒`
}
