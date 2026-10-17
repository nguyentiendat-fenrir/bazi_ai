// One multipart upload with progress (fetch cannot report upload progress).
import { csrf } from './storage'
import { networkError, toApiError } from '@/api/problem'

export interface UploadFields {
  batch_id: string
  rights_status: string
  edition_label: string
  language: string
  external_processing_allowed: boolean
  title?: string
  book_id?: string
}

export interface UploadOutcome {
  outcome: 'accepted' | 'duplicate'
  display_name: string
  book_id: string
  version_id: string | null
  job_id: string | null
  duplicate_of: string | null
}

/** POST /api/v1/uploads; resolves with the result or rejects with ApiError. */
export function uploadFile(file: File, fields: UploadFields, key: string,
                           onProgress: (fraction: number) => void): Promise<UploadOutcome> {
  const form = new FormData()
  form.append('file', file)
  for (const [name, value] of Object.entries(fields)) {
    if (value !== undefined && value !== '') form.append(name, String(value))
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/v1/uploads')
    xhr.withCredentials = true
    xhr.setRequestHeader('Idempotency-Key', key)
    const token = csrf.get()
    if (token) xhr.setRequestHeader('X-CSRF-Token', token)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total)
    }
    xhr.onerror = () => reject(networkError(new Error('upload interrupted')))
    xhr.onload = () => {
      let body: unknown = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        // non-JSON error page from a proxy; handled as a plain status below
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve((body as { data: UploadOutcome }).data)
      } else {
        const headers = new Headers()
        const requestId = xhr.getResponseHeader('X-Request-ID')
        if (requestId) headers.set('X-Request-ID', requestId)
        reject(toApiError(xhr.status, body, headers))
      }
    }
    xhr.send(form)
  })
}
