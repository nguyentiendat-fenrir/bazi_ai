import assert from 'node:assert/strict'
import test from 'node:test'

import { JOB_STATES, formatBytes, label, percent, safeNext, shortId } from '../../src/lib/format.ts'

test('next redirects stay on this origin', () => {
  assert.equal(safeNext('/books?q=a'), '/books?q=a')
  for (const bad of [null, '', 'https://evil.test/', '//evil.test/x', '/\\evil.test', 'books']) {
    assert.equal(safeNext(bad), '/')
  }
})

test('sizes, ids and percentages', () => {
  assert.equal(formatBytes(512), '512 B')
  assert.equal(formatBytes(1536), '1,5 KB')
  assert.equal(formatBytes(5 * 1024 * 1024), '5 MB')
  assert.equal(shortId('0a1b2c3d-4e5f-6789-abcd-ef0123456789'), '0a1b2c3d')
  assert.equal(shortId(null), '—')
  assert.equal(percent(1, 3), '33,3%')
  assert.equal(percent(0, 0), '—')
})

test('every state has a text label; unknown values stay visible', () => {
  assert.deepEqual(label(JOB_STATES, 'failed'), ['Thất bại', 'danger'])
  assert.deepEqual(label(JOB_STATES, 'NEW_STATE'), ['NEW_STATE', 'neutral'])
  assert.deepEqual(label(JOB_STATES, null), ['—', 'neutral'])
})
