'use client'
// One assertion: statement, conditions, exceptions and the quoted sources a reviewer must read
// before approving. Editing makes a new draft revision that keeps the sources.
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call } from '@/api/client'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { ReviewPanel, type ReviewOutcome } from '@/components/ReviewPanel'
import { SourceList } from '@/components/SourceList'
import { ErrorState, Facts, Forbidden, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { ASSERTION_ORIGINS, KNOWLEDGE_STATES } from '@/lib/knowledge'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

const RELATIONS: Record<string, string> = {
  supports: 'ủng hộ', disputes: 'phản bác', qualifies: 'bổ sung điều kiện', exception_to: 'ngoại lệ của', derives_from: 'suy ra từ',
}

export default function AssertionPage() {
  const { assertionId } = useParams<{ assertionId: string }>()
  const router = useRouter()
  const { can } = useSession()
  const assertion = useQuery(`assertion:${assertionId}`, () =>
    call(api.GET('/api/v1/assertions/{assertion_id}', { params: { path: { assertion_id: assertionId } } })))
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({ statement: '', exception_text: '', reason: '' })
  const [error, setError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState<string | null>(null)

  if (!can('library:review')) return <Forbidden what="quản trị tri thức" />
  if (assertion.error) return <ErrorState error={assertion.error} retry={assertion.reload} />
  if (!assertion.data) return <Loading rows={5} />
  const a = assertion.data.data

  const revise = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      const made = await call(api.POST('/api/v1/assertions/{assertion_id}/revisions', {
        params: { path: { assertion_id: a.id } },
        body: { base_revision: a.revision, statement: draft.statement, exception_text: draft.exception_text || null, reason: draft.reason } }))
      setEditing(false)
      router.push(`/knowledge/assertions/${made.data.id}`)
    } catch (caught) {
      setError(caught)
    }
  }
  const reviewed = (result: ReviewOutcome) => {
    setOutcome(`Trạng thái mới: ${KNOWLEDGE_STATES[result.state]?.[0] ?? result.state}.${result.analyses_stale ? ` ${result.analyses_stale} phân tích được đánh dấu cũ.` : ''}`)
    assertion.reload()
  }

  return (
    <>
      <title>Luận điểm · Kho Bát Tự</title>
      <PageHeader title={`Luận điểm ${a.assertion_key}`} back={{ href: '/knowledge/assertions', label: 'Luận điểm' }}
                  description={<>{a.school_key} · bản {a.revision} <StateBadge labels={KNOWLEDGE_STATES} value={a.state} /></>}
                  actions={!editing && (
                    <button type="button" className="button button-secondary" onClick={() => {
                      setDraft({ statement: a.statement, exception_text: a.exception_text ?? '', reason: '' })
                      setEditing(true)
                    }}>Sửa thành bản mới</button>
                  )} />
      <KnowledgeTabs />
      {outcome && <Notice tone="ok">{outcome}</Notice>}
      {a.origin === 'ai_inferred' && <Notice tone="warning">Luận điểm do AI suy ra: đối chiếu kỹ với đoạn trích trước khi duyệt.</Notice>}
      <div className="grid">
        <section className="panel">
          <h2>Nội dung</h2>
          {editing ? (
            <form onSubmit={revise}>
              <div className="field">
                <label htmlFor="as-statement">Luận điểm</label>
                <textarea id="as-statement" rows={3} required value={draft.statement} onChange={(e) => setDraft({ ...draft, statement: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="as-exception">Ngoại lệ</label>
                <textarea id="as-exception" rows={2} value={draft.exception_text} onChange={(e) => setDraft({ ...draft, exception_text: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="as-reason">Lý do sửa</label>
                <input id="as-reason" required value={draft.reason} onChange={(e) => setDraft({ ...draft, reason: e.target.value })} />
              </div>
              <FormError error={error} />
              <div className="actions">
                <button type="button" className="button button-ghost" onClick={() => setEditing(false)}>Hủy</button>
                <button type="submit" className="button">Lưu bản nháp</button>
              </div>
            </form>
          ) : (
            <>
              <p className="statement">{a.statement}</p>
              <Facts items={[
                ['Nguồn gốc', ASSERTION_ORIGINS[a.origin] ?? a.origin],
                ['Ngoại lệ', a.exception_text || <span className="muted">Không ghi</span>],
                ['Điều kiện áp dụng', Object.keys(a.applicability ?? {}).length ? <code>{JSON.stringify(a.applicability)}</code> : <span className="muted">Không giới hạn</span>],
                ['Tạo lúc', formatDateTime(a.created_at)],
              ]} />
              <ReviewPanel kind="assertion" id={a.id} revision={a.revision} state={a.state} onDone={reviewed}
                           checklist={['Đoạn trích nguồn nói đúng điều này', 'Ngoại lệ và điều kiện đã ghi đủ']} />
            </>
          )}
        </section>
        <section className="panel">
          <h2>Nguồn</h2>
          <SourceList sources={a.sources} empty="Chưa gắn nguồn — không thể duyệt." />
          {a.relations.length > 0 && (
            <>
              <h3>Quan hệ</h3>
              <ul className="plain-list">
                {a.relations.map((r) => (
                  <li key={r.id} className="small">
                    {r.from_id === a.id ? 'Luận điểm này' : <Link href={`/knowledge/assertions/${r.from_id}`}>luận điểm khác</Link>}
                    {' '}{RELATIONS[r.relation] ?? r.relation}{' '}
                    {r.to_id === a.id ? 'luận điểm này' : <Link href={`/knowledge/assertions/${r.to_id}`}>luận điểm khác</Link>}
                    {' '}<StateBadge labels={KNOWLEDGE_STATES} value={r.state} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </>
  )
}
