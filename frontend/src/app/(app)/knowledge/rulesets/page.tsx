'use client'
// Rulesets (docs/06): a frozen snapshot of approved rule revisions per method. Activating
// one is a compare-and-swap against the ruleset the reviewer saw in use; the replaced one
// retires and its analyses turn stale.
import Link from 'next/link'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { Empty, ErrorState, Forbidden, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { formatDateTime, shortId } from '@/lib/format'
import { RULESET_STATES } from '@/lib/knowledge'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Ruleset = Schemas['RulesetDTO']

function Members({ id }: { id: string }) {
  const detail = useQuery(`ruleset:${id}`, () => call(api.GET('/api/v1/rulesets/{ruleset_id}', { params: { path: { ruleset_id: id } } })))
  if (detail.error) return <ErrorState error={detail.error} retry={detail.reload} />
  if (!detail.data) return <Loading rows={2} />
  const members = detail.data.data.members
  return members.length === 0 ? <p className="muted small">Không có quy tắc.</p> : (
    <ol className="small">
      {members.map((m) => <li key={m.revision_id}><Link href={`/knowledge/rules/${m.revision_id}`}><code>{m.rule_key}</code></Link></li>)}
    </ol>
  )
}

export default function RulesetsPage() {
  const { can } = useSession()
  const [school, setSchool] = useState('')
  const [method, setMethod] = useState('')
  const [version, setVersion] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [activating, setActivating] = useState<Ruleset | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [activateError, setActivateError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState<string | null>(null)
  const schools = useQuery('knowledge:schools', () => call(api.GET('/api/v1/schools')))
  const methods = useQuery(`knowledge:methods:${school}:approved`, () => call(api.GET('/api/v1/methods', {
    params: { query: { school_id: school || undefined, state: 'approved' } } })))
  const list = useQuery(`rulesets:${school}:${method}`, () => call(api.GET('/api/v1/rulesets', {
    params: { query: { school_id: school || undefined, method_id: method || undefined } } })))

  if (!can('library:review')) return <Forbidden what="quản trị tri thức" />
  const rows = list.data?.data ?? []
  const current = (r: Ruleset) => rows.find((x) => x.method_id === r.method_id && x.state === 'published') ?? null

  const build = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      const made = await call(api.POST('/api/v1/rulesets', { body: { school_id: school, method_id: method, version } }))
      setOutcome(`Đã dựng bộ ${made.data.version} với ${made.data.members_count} quy tắc; chưa dùng cho tới khi kích hoạt.`)
      setVersion('')
      list.reload()
    } catch (caught) {
      setError(caught)
    }
  }

  const activate = async () => {
    if (!activating) return
    setActivateError(null)
    try {
      const done = await call(api.POST('/api/v1/rulesets/{ruleset_id}/activate', {
        params: { path: { ruleset_id: activating.id } },
        body: { expected_current_id: current(activating)?.id ?? null } }))
      setOutcome(`Đang dùng bộ ${done.data.version}; ${done.data.analyses_stale} phân tích được đánh dấu cũ.`)
      setActivating(null)
      list.reload()
    } catch (caught) {
      setActivateError(caught)
      list.reload()
    }
  }

  return (
    <>
      <title>Bộ quy tắc · Kho Bát Tự</title>
      <PageHeader title="Tri thức" description="Bộ quy tắc là ảnh chụp các quy tắc đã duyệt của một phương pháp; phân tích lá số dùng bộ đang dùng." />
      <KnowledgeTabs />
      {outcome && <Notice tone="ok">{outcome}</Notice>}
      <form className="toolbar" onSubmit={build}>
        <div className="field">
          <label htmlFor="rs-school">Trường phái</label>
          <select id="rs-school" value={school} onChange={(e) => { setSchool(e.target.value); setMethod('') }}>
            <option value="">Tất cả</option>
            {schools.data?.data.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="rs-method">Phương pháp đã duyệt</label>
          <select id="rs-method" value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="">Tất cả</option>
            {methods.data?.data.map((m) => <option key={m.id} value={m.id}>{m.school_key} · {m.key}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="rs-version">Phiên bản bộ mới</label>
          <input id="rs-version" value={version} maxLength={50} placeholder="vd. 2026.10" onChange={(e) => setVersion(e.target.value)} />
        </div>
        <button type="submit" className="button" disabled={!school || !method || !version.trim()}>Dựng bộ từ quy tắc đã duyệt</button>
      </form>
      <FormError error={error} />
      {list.error ? <ErrorState error={list.error} retry={list.reload} />
        : !list.data ? <Loading rows={3} />
        : rows.length === 0 ? (
          <Empty title="Chưa có bộ quy tắc">Chọn trường phái và phương pháp đã duyệt rồi dựng bộ đầu tiên.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Danh sách bộ quy tắc</caption>
              <thead><tr><th scope="col">Phiên bản</th><th scope="col">Trường phái · phương pháp</th><th scope="col">Quy tắc</th>
                <th scope="col">Trạng thái</th><th scope="col">Manifest</th><th scope="col">Dựng lúc</th><th scope="col"><span className="visually-hidden">Thao tác</span></th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <button type="button" className="button button-ghost button-small" aria-expanded={open === r.id}
                              onClick={() => setOpen(open === r.id ? null : r.id)}>{r.version}</button>
                      {open === r.id && <Members id={r.id} />}
                    </td>
                    <td>{r.school_key} · {r.method_key}</td>
                    <td>{r.members_count}</td>
                    <td><StateBadge labels={RULESET_STATES} value={r.state} /></td>
                    <td><code className="small">{shortId(r.manifest_hash, 12)}</code></td>
                    <td className="nowrap">{formatDateTime(r.created_at)}</td>
                    <td>{r.state === 'building' && (
                      <button type="button" className="button button-secondary button-small" onClick={() => { setActivateError(null); setActivating(r) }}>
                        Kích hoạt…</button>
                    )}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      <Dialog open={!!activating} onClose={() => setActivating(null)} title="Kích hoạt bộ quy tắc?"
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setActivating(null)}>Không</button>
                <button type="button" className="button" onClick={() => void activate()}>Kích hoạt</button>
              </>}>
        {activating && (
          <>
            <p>Bộ <strong>{activating.version}</strong> ({activating.members_count} quy tắc) sẽ được dùng cho {activating.school_key} · {activating.method_key}.</p>
            {current(activating)
              ? <Notice tone="warning">Bộ {current(activating)!.version} đang dùng sẽ ngưng; các phân tích dùng nó được đánh dấu cũ để đánh giá lại.</Notice>
              : <Notice tone="info">Phương pháp này chưa có bộ đang dùng.</Notice>}
            <FormError error={activateError} />
          </>
        )}
      </Dialog>
    </>
  )
}
