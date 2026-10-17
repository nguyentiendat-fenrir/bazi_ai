'use client'
// Assertions (docs/06): what a school says, tied to quoted evidence; machine candidates
// arrive here as drafts and wait for a reviewer.
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { api, call } from '@/api/client'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { Empty, ErrorState, Forbidden, Loading, PageHeader, StateBadge } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { ASSERTION_ORIGINS, KNOWLEDGE_STATES, STATE_OPTIONS } from '@/lib/knowledge'
import { usePagedList, useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

export default function AssertionsPage() {
  const { can } = useSession()
  const [input, setInput] = useState('')
  const [term, setTerm] = useState('')
  const [school, setSchool] = useState('')
  const [state, setState] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setTerm(input.trim()), 300)
    return () => clearTimeout(timer)
  }, [input])
  const schools = useQuery('knowledge:schools', () => call(api.GET('/api/v1/schools')))
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/assertions', {
    params: { query: { q: term || undefined, school_id: school || undefined, state: (state || undefined) as never, limit: 50, cursor } } })),
  [term, school, state])
  const list = usePagedList(`assertions:${term}:${school}:${state}`, load)

  if (!can('library:review')) return <Forbidden what="quản trị tri thức" />
  return (
    <>
      <title>Luận điểm · Kho Bát Tự</title>
      <PageHeader title="Tri thức" description="Luận điểm của từng trường phái, mỗi luận điểm gắn đoạn trích nguồn." />
      <KnowledgeTabs />
      <div className="toolbar">
        <div className="field grow">
          <label htmlFor="assertion-search">Tìm trong nội dung</label>
          <input id="assertion-search" type="search" value={input} onChange={(e) => setInput(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="assertion-school">Trường phái</label>
          <select id="assertion-school" value={school} onChange={(e) => setSchool(e.target.value)}>
            <option value="">Tất cả</option>
            {schools.data?.data.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="assertion-state">Trạng thái</label>
          <select id="assertion-state" value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">Tất cả</option>
            {STATE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.text}</option>)}
          </select>
        </div>
      </div>
      {list.error && list.items.length === 0 ? <ErrorState error={list.error} retry={list.reload} />
        : list.loading ? <Loading rows={4} />
        : list.items.length === 0 ? (
          <Empty title={term || school || state ? 'Không có luận điểm khớp' : 'Chưa có luận điểm'}>
            Luận điểm được đề xuất khi xử lý sách có trường phái đã duyệt, hoặc tạo qua API kèm đoạn trích.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Danh sách luận điểm</caption>
              <thead><tr><th scope="col">Luận điểm</th><th scope="col">Trường phái</th><th scope="col">Nguồn gốc</th>
                <th scope="col">Bản</th><th scope="col">Trạng thái</th><th scope="col">Tạo lúc</th></tr></thead>
              <tbody>
                {list.items.map((a) => (
                  <tr key={a.id}>
                    <td className="wrap"><Link href={`/knowledge/assertions/${a.id}`}>{a.statement}</Link></td>
                    <td>{a.school_key}</td>
                    <td>{ASSERTION_ORIGINS[a.origin] ?? a.origin}</td>
                    <td>{a.revision}</td>
                    <td><StateBadge labels={KNOWLEDGE_STATES} value={a.state} /></td>
                    <td className="nowrap">{formatDateTime(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {list.hasMore && (
        <div className="pager"><button type="button" className="button button-secondary" onClick={list.loadMore}
                                       disabled={list.loadingMore}>Tải thêm</button></div>
      )}
    </>
  )
}
