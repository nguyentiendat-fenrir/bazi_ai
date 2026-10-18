'use client'
// Rule analysis of a chart (docs/08, docs/09): run the published ruleset of a school and
// method, read what fired with its sources, conflicts between rules, and the full trace.
// Analyses never change: a newer ruleset or a revoked rule marks them stale, and
// re-evaluating makes a new analysis with a diff (docs/06).
import Link from 'next/link'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { Badge, Empty, ErrorState, FormError, Loading, Notice, StateBadge } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { RULE_STATUS } from '@/lib/knowledge'
import { useQuery } from '@/lib/query'

type Analysis = Schemas['AnalysisDTO']
type Claim = Schemas['Claim']

const ANALYSIS_STATES = {
  pending: ['Đang chạy', 'info'], completed: ['Xong', 'ok'], failed: ['Lỗi', 'danger'],
  stale: ['Đã cũ', 'warning'], withdrawn: ['Đã thu hồi', 'neutral'],
} as const

function Source({ id }: { id: string }) {
  const evidence = useQuery(`evidence:${id}`, () => call(api.GET('/api/v1/evidence/{evidence_id}', {
    params: { path: { evidence_id: id } } })))
  if (evidence.error) return <li className="muted small">Nguồn không còn xem được.</li>
  if (!evidence.data) return <li className="muted small">Đang tải nguồn…</li>
  const e = evidence.data.data
  return (
    <li>
      <span className="muted small">Trang {e.physical_page_number}</span>
      <blockquote>{e.quote}</blockquote>
      <Link className="small" href={`/pages/${e.page_revision_id}?from=${e.start_offset}&to=${e.end_offset}`}>Mở trang nguồn</Link>
    </li>
  )
}

function ClaimItem({ claim }: { claim: Claim }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="claim">
      <div className="claim-head">
        <Badge tone="info">{claim.claim_key}</Badge>
        <strong>{String(claim.value)}</strong>
        <span className="muted small">quy tắc <code>{claim.rule_key}</code></span>
      </div>
      <p>{claim.explanation}</p>
      {claim.evidence_ids.length > 0 && (
        <button type="button" className="button button-ghost button-small" aria-expanded={open}
                onClick={() => setOpen(!open)}>{open ? 'Ẩn nguồn' : `Xem nguồn (${claim.evidence_ids.length})`}</button>
      )}
      {open && <ul className="citations">{claim.evidence_ids.map((id) => <Source key={id} id={id} />)}</ul>}
    </li>
  )
}

function Trace({ analysisId }: { analysisId: string }) {
  const trace = useQuery(`trace:${analysisId}`, () => call(api.GET('/api/v1/analyses/{analysis_id}/trace', {
    params: { path: { analysis_id: analysisId }, query: { limit: 200 } } })))
  if (trace.error) return <ErrorState error={trace.error} retry={trace.reload} />
  if (!trace.data) return <Loading rows={2} />
  return (
    <div className="table-wrap">
      <table>
        <caption className="visually-hidden">Từng quy tắc đã xét</caption>
        <thead><tr><th scope="col">Quy tắc</th><th scope="col">Kết quả</th><th scope="col">Chi tiết</th></tr></thead>
        <tbody>
          {trace.data.data.map((t) => (
            <tr key={t.revision_id}>
              <td><code>{t.rule_key}</code> <span className="muted small">bản {t.revision}</span></td>
              <td><StateBadge labels={RULE_STATUS} value={t.status} /></td>
              <td className="wrap small">{describeDetail(t.detail as Record<string, unknown>)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const ENGINE_STATUS: Record<string, string> = {
  fired: 'kích hoạt', not_matched: 'điều kiện không khớp', pending: 'thiếu dữ kiện',
  blocked_exception: 'bị ngoại lệ chặn', dependency_blocked: 'quy tắc phụ thuộc không kích hoạt',
  skipped: 'bỏ qua (vượt giới hạn)',
}
const TRI: Record<string, string> = { true: 'đúng', false: 'sai', null: 'chưa biết' }

function describeDetail(detail: Record<string, unknown>): string {
  if (!detail) return '—'
  const parts = [ENGINE_STATUS[String(detail.status)] ?? String(detail.status ?? '')]
  const reads = (detail.reads ?? {}) as Record<string, unknown>
  const facts = Object.entries(reads).map(([path, value]) => `${path} = ${value === null ? 'không có' : JSON.stringify(value)}`)
  if (facts.length) parts.push(`dữ kiện: ${facts.join('; ')}`)
  if ('when' in detail) parts.push(`điều kiện ${TRI[String(detail.when)]}`)
  if (detail.unless !== null && detail.unless !== undefined) parts.push(`ngoại lệ ${TRI[String(detail.unless)]}`)
  const requires = (detail.requires ?? []) as { status: string }[]
  if (requires.length) parts.push(`phụ thuộc: ${requires.map((r) => ENGINE_STATUS[r.status] ?? r.status).join(', ')}`)
  return parts.filter(Boolean).join(' · ')
}

function describeDiff(diff: Record<string, unknown>): string {
  const count = (key: string) => (Array.isArray(diff[key]) ? (diff[key] as unknown[]).length : 0)
  const parts = [['added', 'thêm'], ['removed', 'bỏ'], ['changed', 'đổi']]
    .filter(([key]) => count(key) > 0).map(([key, word]) => `${word} ${count(key)} kết luận`)
  return parts.length ? `So với lần trước: ${parts.join(', ')}.` : 'Kết luận không đổi so với lần trước.'
}

function AnalysisView({ analysis, onReplaced }: { analysis: Analysis, onReplaced(id: string, diff: unknown): void }) {
  const [error, setError] = useState<unknown>(null)
  const answer = analysis.answer
  const reevaluate = async () => {
    setError(null)
    try {
      const done = await call(api.POST('/api/v1/analyses/{analysis_id}/reevaluate', {
        params: { path: { analysis_id: analysis.id } } }))
      onReplaced(done.data.analysis.id, done.data.diff)
    } catch (caught) {
      setError(caught)
    }
  }
  return (
    <div className="analysis">
      {analysis.status === 'stale' && (
        <Notice tone="warning">
          Kết quả này đã cũ{analysis.stale_reason ? `: ${analysis.stale_reason}` : ''}.{' '}
          <button type="button" className="button button-secondary button-small" onClick={() => void reevaluate()}>Đánh giá lại</button>
        </Notice>
      )}
      <FormError error={error} />
      {!answer ? <p className="muted">Chưa có kết quả.</p> : (
        <>
          {answer.status === 'resource_limit' && <Notice tone="warning">Bộ quy tắc vượt giới hạn tính toán; kết quả chưa đầy đủ.</Notice>}
          <p className="muted small">Bộ quy tắc {String((answer.ruleset as Record<string, unknown>).school_key ?? '')} · {String((answer.ruleset as Record<string, unknown>).method_key ?? '')} {String((answer.ruleset as Record<string, unknown>).version ?? '')}{answer.as_of ? ` · tính tới ${answer.as_of}` : ''}</p>
          {answer.claims.length === 0
            ? <p>Không quy tắc nào kích hoạt với lá số này.</p>
            : <ol className="claims">{answer.claims.map((c, i) => <ClaimItem key={`${c.rule_revision_id}:${i}`} claim={c} />)}</ol>}
          {answer.conflicts.length > 0 && (
            <Notice tone="warning">
              <strong>Các quy tắc cho kết luận khác nhau</strong>
              <ul>{answer.conflicts.map((c) => <li key={c.claim_key}><code>{c.claim_key}</code>: {c.values.map((v) => String(v.value)).join(' / ')}</li>)}</ul>
              Hệ thống không tự chọn bên nào; đọc nguồn của từng quy tắc.
            </Notice>
          )}
          <details>
            <summary>Từng quy tắc đã xét (trace)</summary>
            <Trace analysisId={analysis.id} />
          </details>
        </>
      )}
    </div>
  )
}

export function ChartAnalysis({ chartId }: { chartId: string }) {
  const rulesets = useQuery('rulesets:published', () => call(api.GET('/api/v1/rulesets', { params: { query: { state: 'published' } } })))
  const analyses = useQuery(`chart-analyses:${chartId}`, () => call(api.GET('/api/v1/charts/{chart_id}/analyses', {
    params: { path: { chart_id: chartId } } })))
  const [rulesetId, setRulesetId] = useState('')
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10))
  const [shown, setShown] = useState<string | null>(null)
  const [diff, setDiff] = useState<Record<string, unknown> | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  if (rulesets.error) return <ErrorState error={rulesets.error} retry={rulesets.reload} />
  if (!rulesets.data || !analyses.data) return <Loading rows={2} />
  const published = rulesets.data.data
  const list = analyses.data.data
  const chosen = published.find((r) => r.id === rulesetId) ?? published[0]
  const current = list.find((a) => a.id === shown) ?? list[0]

  const run = async (event: FormEvent) => {
    event.preventDefault()
    if (!chosen) return
    setBusy(true)
    setError(null)
    try {
      const made = await call(api.POST('/api/v1/charts/{chart_id}/analyses', {
        params: { path: { chart_id: chartId } },
        body: { school_id: chosen.school_id, method_id: chosen.method_id, as_of: asOf || null } }))
      setShown(made.data.id)
      analyses.reload()
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  if (published.length === 0 && list.length === 0) {
    return (
      <Empty title="Chưa có bộ quy tắc nào được duyệt">
        Luận lá số theo quy tắc cần chuyên gia duyệt quy tắc từ sách rồi kích hoạt bộ quy tắc của một trường phái.
        Trong lúc chờ, bạn vẫn hỏi đáp về lá số với nguồn sách.
      </Empty>
    )
  }
  return (
    <>
      {published.length > 0 && (
        <form className="toolbar" onSubmit={run}>
          <div className="field">
            <label htmlFor="an-ruleset">Trường phái · phương pháp</label>
            <select id="an-ruleset" value={chosen?.id ?? ''} onChange={(e) => setRulesetId(e.target.value)}>
              {published.map((r) => <option key={r.id} value={r.id}>{r.school_key} · {r.method_key} ({r.version}, {r.members_count} quy tắc)</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="an-asof">Tính tới ngày</label>
            <input id="an-asof" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </div>
          <button type="submit" className="button" disabled={busy}>{busy ? 'Đang luận…' : 'Luận theo quy tắc'}</button>
        </form>
      )}
      <FormError error={error} />
      {list.length > 0 && (
        <>
          {list.length > 1 && (
            <div className="field">
              <label htmlFor="an-history">Các lần luận</label>
              <select id="an-history" value={current?.id} onChange={(e) => setShown(e.target.value)}>
                {list.map((a) => (
                  <option key={a.id} value={a.id}>{formatDateTime(a.created_at)} · {ANALYSIS_STATES[a.status][0]}</option>
                ))}
              </select>
            </div>
          )}
          {current && (
            <>
              <p><Badge tone={ANALYSIS_STATES[current.status][1]}>{ANALYSIS_STATES[current.status][0]}</Badge>{' '}
                <span className="muted small">{formatDateTime(current.created_at)}</span></p>
              {diff && <Notice tone="info">Đã đánh giá lại với bộ quy tắc đang dùng. {describeDiff(diff)}</Notice>}
              <AnalysisView key={current.id} analysis={current}
                            onReplaced={(id, changes) => { setShown(id); setDiff((changes ?? {}) as Record<string, unknown>); analyses.reload() }} />
            </>
          )}
        </>
      )}
    </>
  )
}
