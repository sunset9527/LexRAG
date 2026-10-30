import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (...parts) => readFileSync(resolve(frontendRoot, ...parts), 'utf8')

test('modern SaaS visual foundation uses semantic tokens and no retired structural decorations', () => {
  const globalStyles = readSource('src', 'styles', 'index.css')
  const appLayout = readSource('src', 'components', 'AppLayout.vue')
  const structuralViews = [
    'Chat.vue',
    'Laws.vue',
    'Login.vue',
    'Register.vue',
  ].map((view) => readSource('src', 'views', view)).join('\n')

  for (const token of [
    '--surface-canvas',
    '--surface-raised',
    '--text-primary',
    '--border-subtle',
    '--brand-primary',
    '--focus-ring',
  ]) {
    assert.match(globalStyles, new RegExp(token))
  }

  assert.doesNotMatch(appLayout, /linear-gradient|⚖️/u)
  assert.doesNotMatch(structuralViews, /⚖️|💬|😀|🕸️|📚/u)
})
