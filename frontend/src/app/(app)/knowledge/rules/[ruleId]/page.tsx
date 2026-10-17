'use client'
// One rule revision (docs/06, docs/11): the DSL, its sources, dependencies and fixtures.
// Approving needs the sources, exceptions and passing fixtures checked; it is apart from
// saving a draft. Revoking asks for a reason and shows the analyses that will turn stale.
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { ReviewPanel, type ReviewOutcome } from '@/components/ReviewPanel'
import { SourceList } from '@/components/SourceList'
import { Badge, ErrorState, Facts, Forbidden, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { formatDateTime, shortId } from '@/lib/format'
import { KNOWLEDGE_STATES } from '@/lib/knowledge'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Validation = Schemas['ValidationResult']
const FIXTURE_STATUS: Record<string, string> = {
  fired: 'kích hoạt', not_matched: 'không khớp', pending: 'thiếu dữ kiện',
  blocked_exception: 'bị ngoại lệ chặn', dependency_blocked: 'phụ thuộc chặn',
}

function parseJson(text: string): [unknown, string | null] {
  try {
    return [JSON.parse(text), null]
  } catch (error) {
    return [null, (error as Error).message]
  }
}

export default function RulePage() {
  const { ruleId } = useParams<{ ruleId: string }>()
  const router = useRouter()
  const { can } = useSession()
  const rule = useQuery(`rule:${ruleId}`, () =>
    call(api.GET('/api/v1/rules/{rule_id}', { params: { path: { rule_id: ruleId } } })))
  const [editing, setEditing] = useState(false)
  const [dsl, setDsl] = useState('')
  const [reason, setReason] = useState('')
  const [fixtures, setFixtures] = useState<string | null>(null)
  const [validation, setValidation] = useState<Validation | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [checkError, setCheckError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState<string | null>(null)

  if (!can('library:review')) return <Forbidden what="quản trị tri thức" />
  if (rule.error) return <ErrorState error={rule.error} retry={rule.reload} />
  if (!rule.data) return <Loading rows={6} />
  const r = rule.data.data
  const [, dslProblem] = editing ? parseJson(dsl) : [null, null]
  const [, fixtureProblem] = fixtures !== null ? parseJson(fixtures) : [null, null]

  const revise = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      const made = await call(api.POST('/api/v1/rules/{rule_id}/revisions', {
        params: { path: { rule_id: r.id } },
        body: { base_revision: r.revision, dsl: JSON.parse(dsl), reason } }))
      setEditing(false)
      router.push(`/knowledge/rules/${made.data.id}`)
    } catch (caught) {
      setError(caught)
    }
  }

  const check = async (withFixtures: boolean) => {
    setCheckError(null)
    try {
      const body = { fixtures: withFixtures && fixtures !== null ? JSON.parse(fixtures) : [] }
      const result = await call(api.POST('/api/v1/rules/{rule_id}/validate', { params: { path: { rule_id: r.id } }, body }))
      setValidation(result.data)
      if (withFixtures) {
        setFixtures(null)
        rule.reload()
      }
    } catch (caught) {
      setCheckError(caught)
    }
  }

  const reviewed = (result: ReviewOutcome) => {
    setOutcome(`Trạng thái mới: ${KNOWLEDGE_STATES[result.state]?.[0] ?? result.state}.${result.analyses_stale ? ` ${result.analyses_stale} phân tích được đánh dấu cũ.` : ''}`)
    rule.reload()
  }

  return (
    <>
      <title>{`${r.rule_key} · Quy tắc`}</title>
      <PageHeader title={<code>{r.rule_key}</code>} back={{ href: '/knowledge/rules', label: 'Quy tắc' }}
                  description={<>{r.school_key} · {r.method_key} · bản {r.revision} <StateBadge labels={KNOWLEDGE_STATES} value={r.state} /></>}
                  actions={!editing && (
                    <button type="button" className="button button-secondary" onClick={() => {
                      setDsl(JSON.stringify(r.dsl, null, 2))
                      setReason('')
                      setEditing(true)
                    }}>Sửa thành bản mới</button>
                  )} />
      <KnowledgeTabs />
      {outcome && <Notice tone="ok">{outcome}</Notice>}
      {r.state !== 'approved' && <Notice tone="info">Quy tắc chưa duyệt không vào bộ quy tắc và không chạy trên lá số người dùng.</Notice>}
      <div className="grid">
        <section className="panel">
          <h2>Định nghĩa</h2>
          {editing ? (
            <form onSubmit={revise}>
              <div className="field">
                <label htmlFor="rule-dsl">DSL (JSON)</label>
                <textarea id="rule-dsl" className="code" rows={18} spellCheck={false} value={dsl} onChange={(e) => setDsl(e.target.value)}
                          aria-invalid={!!dslProblem} aria-describedby="rule-dsl-error" />
                {dslProblem && <p id="rule-dsl-error" className="error">JSON không hợp lệ: {dslProblem}</p>}
              </div>
              <div className="field">
                <label htmlFor="rule-reason">Lý do sửa</label>
                <input id="rule-reason" required value={reason} onChange={(e) => setReason(e.target.value)} />
              </div>
              <p className="hint">Bản mới là bản nháp, giữ nguyên <code>rule_key</code>; fixture cần nhập lại cho bản mới.</p>
              <FormError error={error} />
              <div className="actions">
                <button type="button" className="button button-ghost" onClick={() => setEditing(false)}>Hủy</button>
                <button type="submit" className="button" disabled={!!dslProblem}>Lưu bản nháp</button>
              </div>
            </form>
          ) : (
            <>
              <Facts items={[
                ['Giải thích', String((r.dsl as Record<string, unknown>).explanation_template ?? '—')],
                ['Dữ kiện', r.fact_schema_version],
                ['Phụ thuộc', r.requires.length ? r.requires.map((q) => <Link key={q} href={`/knowledge/rules/${q}`}><code>{shortId(q)}</code> </Link>) : 'Không'],
                ['Hash', <code key="h">{shortId(r.dsl_hash, 16)}</code>],
                ['Tạo lúc', formatDateTime(r.created_at)],
              ]} />
              <details>
                <summary>DSL đầy đủ</summary>
                <pre className="code">{JSON.stringify(r.dsl, null, 2)}</pre>
              </details>
              <ReviewPanel kind="rule" id={r.id} revision={r.revision} state={r.state} onDone={reviewed}
                           checklist={['Đã đọc mọi nguồn trích', 'Ngoại lệ của sách đã có trong DSL', 'Fixture dương/âm/thiếu dữ kiện đều đạt']} />
            </>
          )}
        </section>
        <section className="panel">
          <h2>Nguồn</h2>
          <SourceList sources={r.sources} empty="Chưa gắn nguồn — không thể duyệt." />
        </section>
      </div>
      <section className="panel">
        <div className="panel-head">
          <h2>Fixture kiểm thử</h2>
          <div className="actions">
            <button type="button" className="button button-secondary" onClick={() => void check(false)}>Kiểm tra</button>
            {r.state === 'draft' && fixtures === null && (
              <button type="button" className="button button-secondary" onClick={() =>
                setFixtures(JSON.stringify(r.fixtures.length ? r.fixtures : [
                  { name: 'positive', facts: {}, expect: 'fired' },
                  { name: 'negative', facts: {}, expect: 'not_matched' },
                  { name: 'missing', facts: {}, expect: 'pending' }], null, 2))}>Sửa fixture</button>
            )}
          </div>
        </div>
        {fixtures !== null && (
          <div className="field">
            <label htmlFor="rule-fixtures">Fixture (JSON, thay toàn bộ)</label>
            <textarea id="rule-fixtures" className="code" rows={12} spellCheck={false} value={fixtures}
                      onChange={(e) => setFixtures(e.target.value)} aria-invalid={!!fixtureProblem} />
            {fixtureProblem && <p className="error">JSON không hợp lệ: {fixtureProblem}</p>}
            <div className="actions">
              <button type="button" className="button button-ghost" onClick={() => setFixtures(null)}>Hủy</button>
              <button type="button" className="button" disabled={!!fixtureProblem} onClick={() => void check(true)}>Lưu và kiểm tra</button>
            </div>
          </div>
        )}
        <FormError error={checkError} />
        {validation && (
          <div className={`notice notice-${validation.valid && !validation.problem ? 'ok' : 'warning'}`} role="status">
            {validation.valid ? 'DSL hợp lệ.' : 'DSL có lỗi:'}
            {validation.errors.length > 0 && <ul>{validation.errors.map((e, i) => <li key={i}><code>{e.path}</code>: {e.message}</li>)}</ul>}
            {validation.problem && <p>Còn chặn duyệt: {validation.problem}</p>}
          </div>
        )}
        {r.fixtures.length === 0 ? <p className="muted">Chưa có fixture; quy tắc chỉ được duyệt khi có fixture dương, âm và thiếu dữ kiện.</p> : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Fixture của quy tắc</caption>
              <thead><tr><th scope="col">Tên</th><th scope="col">Mong đợi</th><th scope="col">Kết quả</th><th scope="col">Dữ kiện</th></tr></thead>
              <tbody>
                {r.fixtures.map((f) => {
                  const result = validation?.results.find((x) => x.name === f.name)
                  return (
                    <tr key={f.name}>
                      <td><code>{f.name}</code></td>
                      <td>{FIXTURE_STATUS[f.expect] ?? f.expect}</td>
                      <td>{result ? <Badge tone={result.passed ? 'ok' : 'danger'}>{result.passed ? 'đạt' : `trượt: ${FIXTURE_STATUS[result.status] ?? result.status}`}</Badge>
                        : <span className="muted">chưa kiểm</span>}</td>
                      <td><code className="small">{JSON.stringify(f.facts).slice(0, 120)}</code></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {r.reviews.length > 0 && (
        <section className="panel">
          <h2>Lịch sử duyệt</h2>
          <ul className="plain-list">
            {r.reviews.map((v, i) => <li key={i} className="small">{formatDateTime(v.created_at)} · {v.decision} bản {v.base_revision}: {v.reason}</li>)}
          </ul>
        </section>
      )}
    </>
  )
}
