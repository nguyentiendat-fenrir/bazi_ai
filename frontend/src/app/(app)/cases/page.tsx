'use client'
// Cases (docs/11 /cases): four pillars with the source's narrative; book cases come from
// processing, never inferred birth dates.
import Link from 'next/link'
import { useCallback, useState } from 'react'

import { api, call } from '@/api/client'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { Empty, ErrorState, Forbidden, Loading, PageHeader, StateBadge } from '@/components/ui'
import { pillarsLine } from '@/lib/bazi'
import { formatDateTime } from '@/lib/format'
import { CASE_ORIGINS, KNOWLEDGE_STATES, STATE_OPTIONS } from '@/lib/knowledge'
import { usePagedList, useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

export default function CasesPage() {
  const { can } = useSession()
  const [school, setSchool] = useState('')
  const [state, setState] = useState('')
  const [origin, setOrigin] = useState('')
  const schools = useQuery('knowledge:schools', () => call(api.GET('/api/v1/schools')))
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/cases', {
    params: { query: { school_id: school || undefined, state: (state || undefined) as never, origin: (origin || undefined) as never, limit: 50, cursor } } })),
  [school, state, origin])
  const cases = usePagedList(`cases:${school}:${state}:${origin}`, load)

  if (!can('library:review')) return <Forbidden what="quản trị tri thức" />
  return (
    <>
      <title>Ca mẫu · Kho Bát Tự</title>
      <PageHeader title="Tri thức" description="Ca mẫu: tứ trụ cùng lời kể của nguồn; sự kiện là lời kể, không phải kết quả đã kiểm chứng." />
      <KnowledgeTabs />
      <div className="toolbar">
        <div className="field">
          <label htmlFor="case-school">Trường phái</label>
          <select id="case-school" value={school} onChange={(e) => setSchool(e.target.value)}>
            <option value="">Tất cả</option>
            {schools.data?.data.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="case-origin">Nguồn gốc</label>
          <select id="case-origin" value={origin} onChange={(e) => setOrigin(e.target.value)}>
            <option value="">Tất cả</option>
            {Object.entries(CASE_ORIGINS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="case-state">Trạng thái</label>
          <select id="case-state" value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">Tất cả</option>
            {STATE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.text}</option>)}
          </select>
        </div>
      </div>
      {cases.error && cases.items.length === 0 ? <ErrorState error={cases.error} retry={cases.reload} />
        : cases.loading ? <Loading rows={4} />
        : cases.items.length === 0 ? (
          <Empty title={school || state || origin ? 'Không có ca khớp' : 'Chưa có ca mẫu'}>
            Ca trong sách được trích khi xử lý sách có trường phái đã duyệt.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Danh sách ca mẫu</caption>
              <thead><tr><th scope="col">Ca</th><th scope="col">Tứ trụ (năm · tháng · ngày · giờ)</th><th scope="col">Trường phái</th>
                <th scope="col">Nguồn gốc</th><th scope="col">Trạng thái</th><th scope="col">Tạo lúc</th></tr></thead>
              <tbody>
                {cases.items.map((c) => (
                  <tr key={c.id}>
                    <td><Link href={`/cases/${c.id}`}><code>{c.case_key}</code></Link></td>
                    <td className="nowrap">{pillarsLine(c.chart_payload)}</td>
                    <td>{c.school_key}</td>
                    <td>{CASE_ORIGINS[c.origin] ?? c.origin}</td>
                    <td><StateBadge labels={KNOWLEDGE_STATES} value={c.state} /></td>
                    <td className="nowrap">{formatDateTime(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {cases.hasMore && (
        <div className="pager"><button type="button" className="button button-secondary" onClick={cases.loadMore}
                                       disabled={cases.loadingMore}>Tải thêm</button></div>
      )}
    </>
  )
}
