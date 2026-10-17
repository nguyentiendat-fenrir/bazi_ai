'use client'
// One case (docs/11 /cases): four pillars, luck pillars, the source's narrative and claimed
// events, sources and revisions. A missing hour can be filled in a new revision; nothing
// infers a birth date from the pillars.
import { useParams, useRouter } from 'next/navigation'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { ReviewPanel, type ReviewOutcome } from '@/components/ReviewPanel'
import { SourceList } from '@/components/SourceList'
import { ErrorState, Facts, Forbidden, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { BRANCHES, POSITIONS, POSITION_LABELS, STEMS, ganzhi, type PayloadPillars, type Position } from '@/lib/bazi'
import { formatDateTime } from '@/lib/format'
import { CASE_ORIGINS, KNOWLEDGE_STATES } from '@/lib/knowledge'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

interface Payload {
  schema: string
  pillars: PayloadPillars
  sex_for_luck?: string | null
  luck_pillars?: { stem: string, branch: string }[]
  luck_start_ages?: number[] | null
  source_text?: string
}
type PillarDraft = Record<Position, { stem: string, branch: string }>

function eventText(event: unknown): string {
  return typeof event === 'string' ? event : JSON.stringify(event)
}

export default function CasePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const router = useRouter()
  const { can } = useSession()
  const record = useQuery(`case:${caseId}`, () => call(api.GET('/api/v1/cases/{case_id}', { params: { path: { case_id: caseId } } })))
  const [editing, setEditing] = useState(false)
  const [pillars, setPillars] = useState<PillarDraft | null>(null)
  const [narrative, setNarrative] = useState('')
  const [events, setEvents] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  if (!can('library:review')) return <Forbidden what="quản trị tri thức" />
  if (record.error) return <ErrorState error={record.error} retry={record.reload} />
  if (!record.data) return <Loading rows={5} />
  const c = record.data.data
  const payload = c.chart_payload as unknown as Payload

  const startEdit = () => {
    const draft = {} as PillarDraft
    for (const p of POSITIONS) draft[p] = { stem: payload.pillars[p]?.stem ?? '', branch: payload.pillars[p]?.branch ?? '' }
    setPillars(draft)
    setNarrative(c.narrative)
    setEvents(c.claimed_events.map(eventText).join('\n'))
    setReason('')
    setError(null)
    setEditing(true)
  }

  const revise = async (event: FormEvent) => {
    event.preventDefault()
    if (!pillars) return
    setError(null)
    const next: PayloadPillars = {}
    for (const p of POSITIONS) next[p] = pillars[p].stem && pillars[p].branch ? pillars[p] : null
    try {
      await call(api.POST('/api/v1/cases/{case_id}/revisions', {
        params: { path: { case_id: c.id } },
        body: {
          base_revision: c.revision, reason, narrative,
          chart_payload: { ...payload, pillars: next } as unknown as Record<string, never>,
          claimed_events: events.split('\n').map((line) => line.trim()).filter(Boolean),
        } }))
      setEditing(false)
      setOutcome('Đã lưu bản nháp mới; bản đã duyệt trước vẫn được dùng cho tới khi bản mới được duyệt.')
      record.reload()
    } catch (caught) {
      setError(caught)
    }
  }

  const remove = async () => {
    try {
      await call(api.DELETE('/api/v1/cases/{case_id}', { params: { path: { case_id: c.id } } }))
      router.push('/cases')
    } catch (caught) {
      setError(caught)
      setDeleting(false)
    }
  }

  const reviewed = (result: ReviewOutcome) => {
    setOutcome(`Trạng thái mới: ${KNOWLEDGE_STATES[result.state]?.[0] ?? result.state}.`)
    record.reload()
  }

  return (
    <>
      <title>{`${c.case_key} · Ca mẫu`}</title>
      <PageHeader title={<>Ca <code>{c.case_key}</code></>} back={{ href: '/cases', label: 'Ca mẫu' }}
                  description={<>{c.school_key} · {CASE_ORIGINS[c.origin] ?? c.origin} · bản {c.revision} <StateBadge labels={KNOWLEDGE_STATES} value={c.state} /></>}
                  actions={!editing && <>
                    <button type="button" className="button button-secondary" onClick={startEdit}>Sửa thành bản mới</button>
                    {c.origin !== 'book_case' && <button type="button" className="button button-ghost" onClick={() => setDeleting(true)}>Xóa ca</button>}
                  </>} />
      <KnowledgeTabs />
      {outcome && <Notice tone="ok">{outcome}</Notice>}
      {editing && pillars ? (
        <form className="panel" onSubmit={revise}>
          <h2>Bản mới</h2>
          <div className="form-grid">
            {POSITIONS.map((p) => (
              <fieldset key={p} className="field">
                <legend className="label">Trụ {POSITION_LABELS[p].toLowerCase()}{p === 'hour' ? ' (để trống nếu nguồn không ghi)' : ''}</legend>
                <div className="inline-fields">
                  <select aria-label={`Can trụ ${POSITION_LABELS[p].toLowerCase()}`} value={pillars[p].stem}
                          onChange={(e) => setPillars({ ...pillars, [p]: { ...pillars[p], stem: e.target.value } })}>
                    <option value="">—</option>
                    {Object.entries(STEMS).map(([id, text]) => <option key={id} value={id}>{text}</option>)}
                  </select>
                  <select aria-label={`Chi trụ ${POSITION_LABELS[p].toLowerCase()}`} value={pillars[p].branch}
                          onChange={(e) => setPillars({ ...pillars, [p]: { ...pillars[p], branch: e.target.value } })}>
                    <option value="">—</option>
                    {Object.entries(BRANCHES).map(([id, text]) => <option key={id} value={id}>{text}</option>)}
                  </select>
                </div>
              </fieldset>
            ))}
          </div>
          <div className="field">
            <label htmlFor="case-narrative">Lời kể của nguồn</label>
            <textarea id="case-narrative" rows={5} value={narrative} onChange={(e) => setNarrative(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="case-events">Sự kiện nguồn kể (mỗi dòng một sự kiện)</label>
            <textarea id="case-events" rows={4} value={events} onChange={(e) => setEvents(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="case-reason">Lý do sửa</label>
            <input id="case-reason" required value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <FormError error={error} />
          <div className="actions">
            <button type="button" className="button button-ghost" onClick={() => setEditing(false)}>Hủy</button>
            <button type="submit" className="button">Lưu bản nháp</button>
          </div>
        </form>
      ) : (
        <div className="grid">
          <section className="panel">
            <h2>Tứ trụ</h2>
            <div className="table-wrap">
              <table className="pillars">
                <caption className="visually-hidden">Tứ trụ của ca</caption>
                <thead><tr>{POSITIONS.map((p) => <th key={p} scope="col">{POSITION_LABELS[p]}</th>)}</tr></thead>
                <tbody><tr>{POSITIONS.map((p) => {
                  const x = payload.pillars[p]
                  return <td key={p}>{x ? ganzhi(x.stem, x.branch) : <span className="muted">Nguồn không ghi</span>}</td>
                })}</tr></tbody>
              </table>
            </div>
            <Facts items={[
              ['Chiều vận', payload.sex_for_luck === 'male' ? 'Nam' : payload.sex_for_luck === 'female' ? 'Nữ' : 'Không ghi'],
              ['Đại vận', payload.luck_pillars?.length
                ? payload.luck_pillars.map((l, i) => `${ganzhi(l.stem, l.branch)}${payload.luck_start_ages?.[i] != null ? ` (${payload.luck_start_ages[i]})` : ''}`).join(', ')
                : 'Không ghi'],
              ['Tạo lúc', formatDateTime(c.created_at)],
            ]} />
            <ReviewPanel kind="case_revision" id={c.revision_id} revision={c.revision} state={c.state} onDone={reviewed}
                         checklist={['Tứ trụ khớp bảng trong sách', 'Sự kiện chỉ là lời kể của nguồn']} />
          </section>
          <section className="panel">
            <h2>Lời kể</h2>
            <p className="statement">{c.narrative || <span className="muted">Không có</span>}</p>
            {c.claimed_events.length > 0 && (
              <>
                <h3>Sự kiện nguồn kể</h3>
                <ul>{c.claimed_events.map((e, i) => <li key={i}>{eventText(e)}</li>)}</ul>
              </>
            )}
            <h3>Nguồn</h3>
            <SourceList sources={c.sources} />
            <h3>Các bản</h3>
            <ul className="plain-list">
              {c.revisions.map((r) => <li key={r.id} className="small">Bản {r.revision} <StateBadge labels={KNOWLEDGE_STATES} value={r.state} /></li>)}
            </ul>
          </section>
        </div>
      )}
      <Dialog open={deleting} onClose={() => setDeleting(false)} title="Xóa ca mẫu?"
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setDeleting(false)}>Không</button>
                <button type="button" className="button button-danger" onClick={() => void remove()}>Xóa ca</button>
              </>}>
        <p>Ca <code>{c.case_key}</code> và mọi bản của nó bị xóa.</p>
      </Dialog>
    </>
  )
}
