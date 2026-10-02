import assert from 'node:assert/strict'
import test from 'node:test'

import { buildStatuteTree, getQuestionPresets } from '../src/utils/lawPresentation.js'

test('buildStatuteTree includes every ready statute library and excludes document libraries', () => {
  const tree = buildStatuteTree([
    { slug: 'civil-code', name: '中华人民共和国民法典', type: 'statute', status: 'READY', document_count: 1262 },
    { slug: 'labor-law', name: '中华人民共和国劳动法', type: 'statute', status: 'READY', document_count: 107 },
    { slug: 'uploads', name: '劳动仲裁材料', type: 'document', status: 'READY', document_count: 1 },
    { slug: 'indexing-law', name: '索引中法规', type: 'statute', status: 'INDEXING', document_count: 20 },
  ])

  assert.deepEqual(tree.map((item) => item.slug), ['civil-code', 'labor-law'])
  assert.equal(tree[1].count, 107)
})

test('getQuestionPresets returns a law-specific fallback instead of civil-code questions', () => {
  const questions = getQuestionPresets('labor-law')

  assert.ok(questions.length > 0)
  assert.ok(questions.some((question) => question.includes('劳动')))
})
