import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (...parts) => readFileSync(resolve(frontendRoot, ...parts), 'utf8')

test('JWT and BYOK credentials are never persisted in browser storage', () => {
  const authStore = readSource('src', 'stores', 'auth.ts')
  const settingsStore = readSource('src', 'stores', 'settings.ts')
  const client = readSource('src', 'api', 'client.ts')

  for (const source of [authStore, settingsStore, client]) {
    assert.doesNotMatch(source, /localStorage\.(?:getItem|setItem|removeItem)\(['"]lexrag_token/u)
    assert.doesNotMatch(source, /localStorage\.(?:getItem|setItem|removeItem)\(['"]lexrag_user_api_key/u)
  }
  assert.match(client, /withCredentials:\s*true/u)
  assert.match(client, /getRuntimeApiKey\(\)/u)
  assert.match(settingsStore, /const apiKey = ref\(['"]['"]\)/u)
})
