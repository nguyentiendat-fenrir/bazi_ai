'use client'
// Review decisions for one knowledge record (docs/06, docs/11): each decision needs a reason
// and the revision it was taken on; approve is apart from editing and may need a checklist;
// revoke shows what depends on the record first. History is never deleted.
import { useState } from 'react'

import { api, call, idempotencyKey, type Schemas } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { FormError, Notice } from '@/components/ui'
import { formatNumber } from '@/lib/format'
import { IMPACT_KINDS } from '@/lib/knowledge'

type Kind = 'method' | 'concept' | 'term' | 'school_scope' | 'assertion' | 'assertion_relation' | 'rule' | 'case_revision'
type Decision = 'submit' | 'return' | 'approve' | 'reject' | 'revoke'

const ACTIONS: Record<Decision, { label: string, title: string, tone: string }> = {
  submit: { label: 'Gửi duyệt', title: 'Gửi duyệt', tone: 'button-secondary' },
  return: { label: 'Trả về nháp', title: 'Trả về bản nháp', tone: 'button-secondary' },
  approve: { label: 'Duyệt', title: 'Duyệt', tone: '' },
  reject: { label: 'Từ chối', title: 'Từ chối', tone: 'button-danger' },
  revoke: { label: 'Thu hồi…', title: 'Thu hồi', tone: 'button-danger' },
}
const ALLOWED: Record<string, Decision[]> = {
  draft: ['submit', 'approve', 'reject'], in_review: ['return', 'approve', 'reject'], approved: ['revoke'],
}

type Impact = Pick<Schemas['KnowledgeImpactDTO'], 'counts'> & { dependents?: Schemas['Dependents'] }
export interface ReviewOutcome { state: string, analyses_stale?: number | null, terms_approved?: number | null }

export function ReviewPanel({ kind, id, revision, state, checklist, onDone, compact, subject }: {
  kind: Kind, id: string, revision: number, state: string,
  /** What the reviewer confirms having read before approving (rules: sources, exceptions, fixtures). */
  checklist?: string[]
  onDone(result: ReviewOutcome): void
  compact?: boolean
  /** Names the record in button labels when several panels share a screen. */
  subject?: string
}) {
  const [decision, setDecision] = useState<Decision | null>(null)
  const [reason, setReason] = useState('')
  const [checked, setChecked] = useState<boolean[]>([])
  const [impact, setImpact] = useState<Impact | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [key, setKey] = useState('')

  const open = async (next: Decision) => {
    setDecision(next)
    setReason('')
    setChecked((checklist ?? []).map(() => false))
    setError(null)
    setImpact(null)
    setKey(idempotencyKey())
    if (next === 'revoke') {
      try {
        const found = await call(api.GET('/api/v1/knowledge/impact', { params: { query: { entity_kind: kind, entity_id: id } } }))
        setImpact(found.data)
      } catch {
        setImpact({ counts: {} })
      }
    }
  }

  const submit = async () => {
    if (!decision) return
    setBusy(true)
    setError(null)
    try {
      const result = await call(api.POST('/api/v1/reviews', { params: { header: { 'Idempotency-Key': key } },
        body: { entity_kind: kind, entity_id: id, decision, base_revision: revision, reason: reason.trim() } }))
      setDecision(null)
      onDone(result.data)
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  const actions = ALLOWED[state] ?? []
  if (actions.length === 0) return null
  const needsChecks = decision === 'approve' && (checklist?.length ?? 0) > 0
  const ready = reason.trim().length > 0 && (!needsChecks || checked.every(Boolean))
  const counted = impact
    ? Object.entries({ ...impact.counts, ...(impact.dependents ?? {}) }).filter(([, n]) => typeof n === 'number' && n > 0)
    : []
  return (
    <>
      <div className="actions">
        {actions.map((d) => (
          <button key={d} type="button" className={`button ${ACTIONS[d].tone} ${compact ? 'button-small' : ''}`}
                  aria-label={subject ? `${ACTIONS[d].title} ${subject}` : undefined}
                  onClick={() => void open(d)}>{ACTIONS[d].label}</button>
        ))}
      </div>
      <Dialog open={!!decision} onClose={() => setDecision(null)}
              title={decision ? `${ACTIONS[decision].title}${subject ? ` ${subject}` : ''}?` : ''}
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setDecision(null)}>Không</button>
                <button type="button" className={`button ${decision ? ACTIONS[decision].tone : ''}`}
                        disabled={!ready || busy} onClick={() => void submit()}>Xác nhận</button>
              </>}>
        {decision === 'revoke' && (
          impact === null ? <p className="muted">Đang tính ảnh hưởng…</p>
            : counted.length === 0 ? <Notice tone="info">Không có bản ghi nào đang dựa vào mục này.</Notice>
            : <Notice tone="warning">Đang dựa vào mục này: {counted.map(([k, n]) => `${formatNumber(n)} ${IMPACT_KINDS[k] ?? k}`).join(', ')}. Phân tích liên quan sẽ bị đánh dấu cũ; lịch sử được giữ.</Notice>
        )}
        {needsChecks && (
          <fieldset className="field">
            <legend className="label">Đã xem trước khi duyệt</legend>
            {checklist!.map((item, i) => (
              <label key={item} className="checkbox">
                <input type="checkbox" checked={checked[i] ?? false}
                       onChange={(e) => setChecked(checked.map((c, j) => (j === i ? e.target.checked : c)))} />
                <span>{item}</span>
              </label>
            ))}
          </fieldset>
        )}
        <div className="field">
          <label htmlFor="review-reason">Lý do</label>
          <textarea id="review-reason" rows={3} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <p className="muted small">Áp dụng cho bản {revision}; nếu ai đó vừa sửa, bạn sẽ được báo để xem bản mới.</p>
        <FormError error={error} />
      </Dialog>
    </>
  )
}
