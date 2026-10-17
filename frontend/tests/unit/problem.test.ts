import assert from 'node:assert/strict'
import test from 'node:test'

import { ApiError, describe, networkError, toApiError } from '../../src/api/problem.ts'

test('problem details become a typed error with field hints and headers', () => {
  const headers = new Headers({ 'Retry-After': '120', ETag: '"7"', 'X-Request-ID': 'req-12345678' })
  const error = toApiError(422, {
    type: 'about:blank', title: 'Validation failed', status: 422, code: 'VALIDATION_ERROR',
    detail: null, field_errors: [{ path: 'body.reason', message: 'too short' }], request_id: null,
  }, headers)
  assert.ok(error instanceof ApiError)
  assert.equal(error.code, 'VALIDATION_ERROR')
  assert.equal(error.fieldError('body.reason'), 'too short')
  assert.equal(error.requestId, 'req-12345678')
  assert.equal(error.etag, '"7"')
  assert.equal(error.retryAfter, 120)
  assert.match(describe(error), /Dữ liệu chưa hợp lệ/)
})

test('non-JSON bodies and unknown codes still produce something readable', () => {
  const error = toApiError(502, 'Bad gateway', null)
  assert.equal(error.code, 'SERVER_ERROR')
  const unknown = toApiError(409, { code: 'SOMETHING_NEW', title: 'Conflict', detail: 'Exact reason' })
  assert.equal(describe(unknown), 'Exact reason')
  assert.equal(networkError(new TypeError('fetch failed')).code, 'NETWORK_ERROR')
})
