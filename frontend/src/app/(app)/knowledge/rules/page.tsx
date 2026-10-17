'use client'
// Rules by school and method (docs/11 /knowledge/rules). Only approved revisions can enter a
// ruleset; drafts are listed for review and never run on user charts.
import Link from 'next/link'
import { useCallback, useState } from 'react'

import { api, call } from '@/api/client'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { Empty, ErrorState, Forbidden, Loading, PageHeader, StateBadge } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { KNOWLEDGE_STATES, STATE_OPTIONS } from '@/lib/knowledge'
import { usePagedList, useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

export default function RulesPage() {
  const { can } = useSession()
  const [school, setSchool] = useState('')
  const [method, setMethod] = useState('')
  const [state, setState] = useState('')
  const schools = useQuery('knowledge:schools', () => call(api.GET('/api/v1/schools')))
  const methods = useQuery(`knowledge:methods:${school}`, () => call(api.GET('/api/v1/methods', {
    params: { query: { school_id: school || undefined } } })))
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/rules', {
    params: { query: { school_id: school || undefined, method_id: method || undefined, state: (state || undefined) as never, limit: 50, cursor } } })),
  [school, method, state])
  const rules = usePagedList(`rules:${school}:${method}:${state}`, load)

  if (!can('library:review')) return <Forbidden what="quản trị tri thức" />
  return (
    <>
      <title>Quy tắc · Kho Bát Tự</title>
      <PageHeader title="Tri thức" description="Quy tắc mệnh lý viết bằng DSL, mỗi quy tắc gắn nguồn và fixture kiểm thử." />
      <KnowledgeTabs />
      <div className="toolbar">
        <div className="field">
          <label htmlFor="rule-school">Trường phái</label>
          <select id="rule-school" value={school} onChange={(e) => { setSchool(e.target.value); setMethod('') }}>
            <option value="">Tất cả</option>
            {schools.data?.data.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="rule-method">Phương pháp</label>
          <select id="rule-method" value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="">Tất cả</option>
            {methods.data?.data.map((m) => <option key={m.id} value={m.id}>{m.school_key} · {m.key}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="rule-state">Trạng thái</label>
          <select id="rule-state" value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">Tất cả</option>
            {STATE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.text}</option>)}
          </select>
        </div>
      </div>
      {rules.error && rules.items.length === 0 ? <ErrorState error={rules.error} retry={rules.reload} />
        : rules.loading ? <Loading rows={4} />
        : rules.items.length === 0 ? (
          <Empty title={school || method || state ? 'Không có quy tắc khớp' : 'Chưa có quy tắc'}>
            Quy tắc được soạn qua API từ luận điểm đã có nguồn; chuyên gia duyệt từng bản ở đây.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Danh sách quy tắc</caption>
              <thead><tr><th scope="col">Quy tắc</th><th scope="col">Trường phái · phương pháp</th>
                <th scope="col">Bản</th><th scope="col">Trạng thái</th><th scope="col">Tạo lúc</th></tr></thead>
              <tbody>
                {rules.items.map((r) => (
                  <tr key={r.id}>
                    <td><Link href={`/knowledge/rules/${r.id}`}><code>{r.rule_key}</code></Link></td>
                    <td>{r.school_key} · {r.method_key}</td>
                    <td>{r.revision}</td>
                    <td><StateBadge labels={KNOWLEDGE_STATES} value={r.state} /></td>
                    <td className="nowrap">{formatDateTime(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {rules.hasMore && (
        <div className="pager"><button type="button" className="button button-secondary" onClick={rules.loadMore}
                                       disabled={rules.loadingMore}>Tải thêm</button></div>
      )}
    </>
  )
}
