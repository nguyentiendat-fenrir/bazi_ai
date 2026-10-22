'use client'
// One curated definition beside its evidence (docs/10 · Biên soạn): read, open the source
// pages, then approve, reject, edit (a new draft that keeps the sources) or ask for a rewrite.
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call } from '@/api/client'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { ReviewPanel, type ReviewOutcome } from '@/components/ReviewPanel'
import { ErrorState, Forbidden, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { withBase } from '@/lib/base'
import { CURATION_PROBLEMS, CURATION_STATUSES, CURATION_VERDICTS, KNOWLEDGE_STATES } from '@/lib/knowledge'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

const SPEAKERS: Record<string, string> = {
  original_author: 'nguyên văn', commentator: 'lời bình', translator: 'người dịch', editor: 'biên tập', unknown: 'chưa rõ',
}

export default function CuratedDefinitionPage() {
  const { conceptId } = useParams<{ conceptId: string }>()
  const router = useRouter()
  const { can } = useSession()
  const item = useQuery(`curation:${conceptId}`, () => call(api.GET('/api/v1/curation/definitions/{concept_id}',
    { params: { path: { concept_id: conceptId } } })))
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({ description: '', reason: '' })
  const [note, setNote] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState<string | null>(null)

  if (!can('library:review')) return <Forbidden what="biên soạn định nghĩa" />
  if (item.error) return <ErrorState error={item.error} retry={item.reload} />
  if (!item.data) return <Loading rows={6} />
  const d = item.data.data
  const latest = d.revision === d.latest_revision
  const open = latest && (d.state === 'draft' || d.state === 'in_review')
  const handle = Object.fromEntries(d.evidence.map((e, i) => [e.id, `E${i + 1}`]))

  const reviewed = (result: ReviewOutcome) => {
    setOutcome(`Trạng thái mới: ${KNOWLEDGE_STATES[result.state]?.[0] ?? result.state}.`)
    item.reload()
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      const made = await call(api.POST('/api/v1/concepts/{concept_id}/revisions', {
        params: { path: { concept_id: d.concept_id } },
        body: { base_revision: d.revision, description: draft.description, reason: draft.reason } }))
      setEditing(false)
      router.push(`/knowledge/curation/${made.data.id}`)
    } catch (caught) {
      setError(caught)
    }
  }

  const rewrite = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      await call(api.POST('/api/v1/curation/definitions/{concept_id}/rewrite', {
        params: { path: { concept_id: d.concept_id } }, body: { note } }))
      setNote('')
      setOutcome('Đã ghi yêu cầu. Lần chạy curate tiếp theo sẽ soạn lại định nghĩa này theo ghi chú.')
      item.reload()
    } catch (caught) {
      setError(caught)
    }
  }

  return (
    <>
      <title>{`${d.label} · Biên soạn`}</title>
      <PageHeader title={d.label} back={{ href: '/knowledge/curation', label: 'Biên soạn' }}
                  description={<>{d.school_key} · <code>{d.canonical_key}</code> · bản {d.revision}{' '}
                    <StateBadge labels={KNOWLEDGE_STATES} value={d.state} />{' '}
                    <StateBadge labels={CURATION_STATUSES} value={d.status} />{' '}
                    {d.llm_verdict && <StateBadge labels={CURATION_VERDICTS} value={d.llm_verdict} />}</>}
                  actions={<Link className="button button-ghost" href={`/knowledge/concepts/${d.concept_id}`}>Trang khái niệm</Link>} />
      <KnowledgeTabs />
      {!latest && <Notice tone="warning">Đây là bản cũ; đã có bản {d.latest_revision}.</Notice>}
      {outcome && <Notice tone="ok">{outcome}</Notice>}
      <div className="grid">
        <section className="panel">
          <h2>Định nghĩa</h2>
          {editing ? (
            <form onSubmit={save}>
              <div className="field">
                <label htmlFor="def-text">Định nghĩa</label>
                <textarea id="def-text" rows={7} value={draft.description}
                          onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="def-reason">Lý do sửa</label>
                <input id="def-reason" required value={draft.reason} onChange={(e) => setDraft({ ...draft, reason: e.target.value })} />
              </div>
              <p className="hint">Lưu thành bản nháp mới, giữ nguyên nguồn; sau đó duyệt bản mới.</p>
              <FormError error={error} />
              <div className="actions">
                <button type="button" className="button button-ghost" onClick={() => setEditing(false)}>Hủy</button>
                <button type="submit" className="button">Lưu bản nháp</button>
              </div>
            </form>
          ) : (
            <>
              <p className="definition">{d.definition}</p>
              {d.essential_notes && <p><strong>Lưu ý thiết yếu:</strong> {d.essential_notes}</p>}
              {d.claims.length > 0 && (
                <>
                  <h3>Các ý và nguồn</h3>
                  <ul className="plain-list">
                    {d.claims.map((c, i) => (
                      <li key={i}>{c.text}{' '}
                        {c.evidence_ids.map((e) => <a key={e} href={`#ev-${e}`} className="badge badge-info">{handle[e] ?? '?'}</a>)}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {open && (
                <>
                  <div className="actions">
                    <button type="button" className="button button-secondary" onClick={() => {
                      setDraft({ description: d.definition, reason: '' })
                      setEditing(true)
                    }}>Sửa rồi duyệt</button>
                  </div>
                  <ReviewPanel kind="concept" id={d.concept_id} revision={d.revision} state={d.state} onDone={reviewed}
                               checklist={['Đã đọc các đoạn nguồn bên cạnh', 'Định nghĩa không trộn nghĩa của trường phái khác']} />
                </>
              )}
            </>
          )}
        </section>
        <section className="panel">
          <h2>Máy kiểm</h2>
          {d.llm_verdict ? (
            <p><StateBadge labels={CURATION_VERDICTS} value={d.llm_verdict} /> <span className="small muted">({d.review_model})</span></p>
          ) : <p className="muted">Chưa kiểm.</p>}
          {d.llm_problems.length > 0 && (
            <ul className="plain-list">
              {d.llm_problems.map((p, i) => <li key={i}><strong>{CURATION_PROBLEMS[p.kind] ?? p.kind}:</strong> {p.detail}</li>)}
            </ul>
          )}
          {d.issues.length > 0 && (
            <>
              <h3>Ghi chú khi soạn</h3>
              <ul className="plain-list small">{d.issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul>
            </>
          )}
          <p className="small muted">Soạn bởi {d.compose_model ?? '—'} · {d.independent_sources} sách độc lập</p>
          {open && (
            <form onSubmit={rewrite}>
              <div className="field">
                <label htmlFor="rewrite-note">Yêu cầu viết lại (tùy chọn ghi chú)</label>
                <textarea id="rewrite-note" rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
              </div>
              {d.status === 'rewrite_requested' && <p className="hint">Đang chờ viết lại: {d.rewrite_note || '(không ghi chú)'}</p>}
              <button type="submit" className="button button-secondary">Yêu cầu viết lại</button>
            </form>
          )}
          <FormError error={editing ? null : error} />
        </section>
      </div>
      <section className="panel">
        <h2>Nguồn</h2>
        {d.evidence.length === 0 ? <p className="muted">Không có đoạn nguồn nào được dẫn.</p> : (
          <ol className="plain-list">
            {d.evidence.map((e, i) => (
              <li key={e.id} id={`ev-${e.id}`}>
                <span className="badge badge-info">E{i + 1}</span>{' '}
                <strong>{e.book_title}</strong> · tr.{e.page} · {SPEAKERS[e.speaker_layer] ?? e.speaker_layer}{' '}
                <a href={withBase(`/pages/${e.page_revision_id}?from=${e.start_offset}&to=${e.end_offset}`)}>Mở trang</a>
                <blockquote>{e.quote}</blockquote>
              </li>
            ))}
          </ol>
        )}
      </section>
    </>
  )
}
