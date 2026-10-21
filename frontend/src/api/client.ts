// Typed API client generated from contracts/openapi.json (docs/10).
//
// Cookie session + X-CSRF-Token on unsafe methods. `call` unwraps the envelope result or
// throws ApiError; a 401 anywhere except the login form signs the user out.
import createClient, { type Middleware } from 'openapi-fetch'

import { BASE_PATH } from '@/lib/base'
import { csrf } from '@/lib/storage'
import { ApiError, networkError, toApiError } from './problem'
import type { components, paths } from './schema'

export type Schemas = components['schemas']

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

const security: Middleware = {
  onRequest({ request }) {
    const token = csrf.get()
    if (UNSAFE.has(request.method) && token) request.headers.set('X-CSRF-Token', token)
    return request
  },
}

export const api = createClient<paths>({ baseUrl: BASE_PATH, credentials: 'same-origin' })
api.use(security)

type Listener = (error: ApiError) => void
let onSessionLost: Listener | null = null

/** The session provider registers here to react to 401 / missing CSRF anywhere. */
export function setSessionLostListener(listener: Listener | null): void {
  onSessionLost = listener
}

/** For requests made outside `call` (multipart uploads): end the session on 401/CSRF. */
export function reportAuthFailure(error: ApiError): void {
  if (error.status === 401 || error.code === 'CSRF_FAILED') onSessionLost?.(error)
}

interface Result<T> {
  data?: T
  error?: unknown
  response: Response
}

/** Await an openapi-fetch call; return its body or throw ApiError. */
export async function call<T>(request: Promise<Result<T>>,
                              options: { quietAuth?: boolean } = {}): Promise<T> {
  let result: Result<T>
  try {
    result = await request
  } catch (cause) {
    throw networkError(cause)
  }
  const { data, error, response } = result
  if (response.ok) return data as T
  const problem = toApiError(response.status, error, response.headers)
  if (!options.quietAuth && (problem.status === 401 || problem.code === 'CSRF_FAILED')) {
    onSessionLost?.(problem)
  }
  throw problem
}

/** Opaque key for one logical mutation; reuse it when retrying the same request. */
export function idempotencyKey(): string {
  return crypto.randomUUID()
}

/** ETag header value for a revision-based If-Match (books use their integer revision). */
export function ifMatch(revision: string | number): string {
  return `"${revision}"`
}
