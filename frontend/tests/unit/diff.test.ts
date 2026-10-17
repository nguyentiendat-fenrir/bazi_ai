import assert from 'node:assert/strict'
import test from 'node:test'

import { diffWords, rebase } from '../../src/lib/diff.ts'

test('word diff keeps whitespace and marks only what changed', () => {
  const parts = diffWords('Giáp Tý sinh mùa xuân', 'Giáp Tý sinh mùa đông')
  assert.deepEqual(parts, [
    { kind: 'same', text: 'Giáp Tý sinh mùa ' },
    { kind: 'removed', text: 'xuân' },
    { kind: 'added', text: 'đông' },
  ])
  const joined = (kinds: string[]) => parts.filter((p) => kinds.includes(p.kind)).map((p) => p.text).join('')
  assert.equal(joined(['same', 'removed']), 'Giáp Tý sinh mùa xuân')
  assert.equal(joined(['same', 'added']), 'Giáp Tý sinh mùa đông')
  assert.deepEqual(diffWords('', 'mới'), [{ kind: 'added', text: 'mới' }])
})

test('rebase keeps untouched edits, drops agreed ones, flags real conflicts', () => {
  const base = [
    { ordinal: 0, text: 'thuong quan', speaker_layer: 'unknown' },
    { ordinal: 1, text: 'thuc than', speaker_layer: 'unknown' },
    { ordinal: 2, text: 'kiep tai', speaker_layer: 'unknown' },
  ]
  const latest = [
    { ordinal: 0, text: 'thuong quan', speaker_layer: 'commentator' },   // they changed the layer
    { ordinal: 1, text: 'thực thần', speaker_layer: 'unknown' },          // same fix as mine
    { ordinal: 2, text: 'kiếp tài!', speaker_layer: 'unknown' },          // a different fix
  ]
  const { edits, conflicts } = rebase(base, latest, {
    0: { text: 'thương quan' },
    1: { text: 'thực thần' },
    2: { text: 'kiếp tài' },
    7: { text: 'gone' },
  })
  assert.deepEqual(edits, { 0: { text: 'thương quan' }, 2: { text: 'kiếp tài' } })
  assert.deepEqual(conflicts, [2, 7])
})
