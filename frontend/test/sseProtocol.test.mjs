import assert from 'node:assert/strict'
import test from 'node:test'

import { buildQueryRunEventsUrl, parseEventPayload } from '../src/api/sseProtocol.js'
import { formatElapsedSeconds } from '../src/utils/queryRunProgress.js'

test('parseEventPayload returns a plain object for a valid SSE payload', () => {
  assert.deepEqual(
    parseEventPayload('{"stage":"routing","status":"completed"}'),
    { stage: 'routing', status: 'completed' },
  )
})

test('parseEventPayload rejects malformed or non-object SSE payloads', () => {
  assert.equal(parseEventPayload('{not-json}'), null)
  assert.equal(parseEventPayload('["not-an-event"]'), null)
  assert.equal(parseEventPayload('null'), null)
})

test('buildQueryRunEventsUrl keeps the API prefix and encodes the query identifier', () => {
  assert.equal(
    buildQueryRunEventsUrl('/api/', 'query/id'),
    '/api/query-runs/query%2Fid/events',
  )
})

test('formatElapsedSeconds uses whole non-negative seconds', () => {
  assert.equal(formatElapsedSeconds(1_000, 6_999), '5 秒')
  assert.equal(formatElapsedSeconds(8_000, 7_000), '0 秒')
})
