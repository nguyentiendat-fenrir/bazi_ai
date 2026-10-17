'use client'
// Own charts (docs/11 /charts): search by profile label, open, start a new one.
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { api, call } from '@/api/client'
import { Badge, Empty, ErrorState, Loading, PageHeader } from '@/components/ui'
import { POLICIES, pairLabel } from '@/lib/bazi'
import { formatDateTime } from '@/lib/format'
import { usePagedList } from '@/lib/query'

export default function ChartsPage() {
  const [input, setInput] = useState('')
  const [term, setTerm] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setTerm(input.trim()), 300)
    return () => clearTimeout(timer)
  }, [input])
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/charts', {
    params: { query: { q: term || undefined, limit: 50, cursor } } })), [term])
  const charts = usePagedList(`charts:${term}`, load)

  return (
    <>
      <title>Lá số · Kho Bát Tự</title>
      <PageHeader title="Lá số" description="Lá số của bạn; dữ liệu sinh được mã hóa, chỉ bạn xem được."
                  actions={<Link className="button" href="/charts/new">Lập lá số mới</Link>} />
      <div className="toolbar">
        <div className="field grow">
          <label htmlFor="chart-search">Tìm theo tên hồ sơ</label>
          <input id="chart-search" type="search" value={input} onChange={(e) => setInput(e.target.value)} />
        </div>
      </div>
      {charts.error && charts.items.length === 0 ? <ErrorState error={charts.error} retry={charts.reload} />
        : charts.loading ? <Loading rows={4} />
        : charts.items.length === 0 ? (
          <Empty title={term ? 'Không có lá số khớp' : 'Chưa có lá số nào'}
                 action={<Link className="button" href="/charts/new">Lập lá số</Link>}>
            {term ? `Không có hồ sơ nào tên chứa “${term}”.` : 'Lập lá số từ ngày giờ sinh dương lịch hoặc âm lịch.'}
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Danh sách lá số</caption>
              <thead>
                <tr><th scope="col">Hồ sơ</th><th scope="col">Năm</th><th scope="col">Tháng</th><th scope="col">Ngày</th>
                  <th scope="col">Giờ</th><th scope="col">Cách tính</th><th scope="col">Lập lúc</th></tr>
              </thead>
              <tbody>
                {charts.items.map((c) => (
                  <tr key={c.id}>
                    <td><Link href={`/charts/${c.id}`}>{c.profile_label ?? 'Lá số không tên'}</Link>
                      {c.validation_status === 'partial' && <> <Badge tone="warning">thiếu trụ</Badge></>}</td>
                    <td>{pairLabel(c.pillars.year)}</td>
                    <td>{pairLabel(c.pillars.month)}</td>
                    <td>{pairLabel(c.pillars.day)}</td>
                    <td>{c.pillars.hour ? pairLabel(c.pillars.hour) : <span className="muted">—</span>}</td>
                    <td>{POLICIES[c.policy_id] ?? c.policy_id}</td>
                    <td className="nowrap">{formatDateTime(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {charts.hasMore && (
        <div className="pager"><button type="button" className="button button-secondary" onClick={charts.loadMore}
                                       disabled={charts.loadingMore}>Tải thêm</button></div>
      )}
    </>
  )
}
