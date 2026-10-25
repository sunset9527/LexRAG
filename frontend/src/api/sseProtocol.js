/** Parse only object-shaped SSE payloads; invalid frames are ignored safely. */
export function parseEventPayload(raw) {
  try {
    const payload = JSON.parse(raw)
    return payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : null
  } catch {
    return null
  }
}

export function buildQueryRunEventsUrl(apiBaseUrl, queryId) {
  return `${apiBaseUrl.replace(/\/$/, '')}/query-runs/${encodeURIComponent(queryId)}/events`
}
