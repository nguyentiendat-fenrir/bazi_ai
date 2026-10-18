'use client'
// Which school a book version (or a range of its pages) belongs to (docs/06 · trường phái).
// A scope is a proposal until reviewed; approving it re-classifies the version's chunks
// in a new job, and only then do concepts, assertions and cases get proposed for it.
import Link from 'next/link'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call } from '@/api/client'
import { ReviewPanel, type ReviewOutcome } from '@/components/ReviewPanel'
import { ErrorState, FormError, Loading, Notice, StateBadge } from '@/components/ui'
import { KNOWLEDGE_STATES } from '@/lib/knowledge'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

export function SchoolScopesPanel({ versionId, pageCount }: { versionId: string, pageCount?: number | null }) {
  const { can } = useSession()
  const reviewer = can('library:review')
  const scopes = useQuery(`scopes:${versionId}`, () => call(api.GET('/api/v1/book-versions/{version_id}/school-scopes', {
    params: { path: { version_id: versionId } } })))
  const schools = useQuery('scopes:schools', () => call(api.GET('/api/v1/schools')))
  const [form, setForm] = useState({ school_id: '', first_page: '', last_page: '', reason: '' })
  const [error, setError] = useState<unknown>(null)
  const [job, setJob] = useState<string | null>(null)

  if (scopes.error) return <ErrorState error={scopes.error} retry={scopes.reload} />
  if (!scopes.data) return <Loading rows={2} />

  const add = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      await call(api.POST('/api/v1/book-versions/{version_id}/school-scopes', {
        params: { path: { version_id: versionId } },
        body: { school_id: form.school_id, reason: form.reason.trim(),
                first_page: form.first_page ? Number(form.first_page) : null,
                last_page: form.last_page ? Number(form.last_page) : null } }))
      setForm({ school_id: '', first_page: '', last_page: '', reason: '' })
      scopes.reload()
    } catch (caught) {
      setError(caught)
    }
  }
  const reviewed = (result: ReviewOutcome) => {
    if (result.job_id) setJob(result.job_id)
    scopes.reload()
  }

  const list = scopes.data.data
  return (
    <div className="scopes">
      {list.length === 0 ? <p className="muted">Chưa gán trường phái. Gán để hệ thống đề xuất khái niệm, luận điểm và ca mẫu theo đúng trường phái.</p> : (
        <ul className="plain-list">
          {list.map((s) => (
            <li key={s.id} className="scope">
              <div>
                <strong>{schools.data?.data.find((x) => x.id === s.school_id)?.label ?? s.school_key}</strong>{' '}
                <span className="muted small">{s.first_page ? `trang ${s.first_page}–${s.last_page ?? '…'}` : 'cả phiên bản'} · {s.reason}</span>{' '}
                <StateBadge labels={KNOWLEDGE_STATES} value={s.state} />
              </div>
              {reviewer && <ReviewPanel kind="school_scope" id={s.id} revision={1} state={s.state} compact
                                        subject={`trường phái ${s.school_key}`} onDone={reviewed} />}
            </li>
          ))}
        </ul>
      )}
      {job && <Notice tone="info">Đã tạo job phân loại lại theo trường phái. <Link href={`/jobs/${job}`}>Theo dõi job</Link></Notice>}
      {reviewer && (
        <form className="inline-form" onSubmit={add}>
          <div className="field">
            <label htmlFor="scope-school">Trường phái</label>
            <select id="scope-school" required value={form.school_id} onChange={(e) => setForm({ ...form, school_id: e.target.value })}>
              <option value="">Chọn…</option>
              {schools.data?.data.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="scope-from">Từ trang</label>
            <input id="scope-from" type="number" min={1} max={pageCount ?? undefined} value={form.first_page}
                   onChange={(e) => setForm({ ...form, first_page: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="scope-to">Đến trang</label>
            <input id="scope-to" type="number" min={1} max={pageCount ?? undefined} value={form.last_page}
                   onChange={(e) => setForm({ ...form, last_page: e.target.value })} />
          </div>
          <div className="field grow">
            <label htmlFor="scope-reason">Căn cứ</label>
            <input id="scope-reason" required maxLength={500} placeholder="vd. lời tựa nói rõ sách theo Manh phái"
                   value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
          </div>
          <button type="submit" className="button button-secondary">Đề xuất</button>
        </form>
      )}
      <FormError error={error} />
      <p className="hint">Để trống trang là cả phiên bản. Trường phái chỉ có hiệu lực sau khi được duyệt.</p>
    </div>
  )
}
