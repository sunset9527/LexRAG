import { describe, expect, it } from 'vitest'

import { buildQueryRunEventsUrl, parseEventPayload } from './sseProtocol.js'

describe('SSE protocol helpers', () => {
  it('parses object events and rejects non-object frames', () => {
    expect(parseEventPayload('{"stage":"routing"}')).toEqual({ stage: 'routing' })
    expect(parseEventPayload('["not-an-event"]')).toBeNull()
  })

  it('keeps the API prefix and encodes a query ID', () => {
    expect(buildQueryRunEventsUrl('/api/', 'query/id')).toBe('/api/query-runs/query%2Fid/events')
  })
})
