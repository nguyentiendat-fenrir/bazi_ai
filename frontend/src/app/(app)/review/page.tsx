'use client'
// Source review queue (docs/11 /review/ocr): pages the pipeline could not accept alone.
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useCallback, useState } from 'react'

import { api, call } from '@/api/client'
import { Empty, ErrorState, Forbidden, Loading, PageHeader, StateBadge } from '@/components/ui'
import { REVIEW_REASONS, REVIEW_STATES, SEVERITIES, formatDateTime } from '@/lib/format'
import { usePagedList } from '@/lib/query'
import { useSession } from '@/lib/session'

type State = 'open' | 'in_progress' | 'resolved' | 'dismissed'

function Queue() {
  const version = useSearchParams().get('version')
  const [state, setState] = useState<State>('open')
  const [reason, setReason] = useState('')
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/review-items', {
    params: { query: { scope: 'page', state, reason: reason || undefined, book_version_id: version,
                       limit: 50, cursor } },
  })), [state, reason, version])
  const items = usePagedList(`review:${state}:${reason}:${version}`, load)

  return (
    <>
      <div className="toolbar">
        <div className="field">
          <label htmlFor="review-state">Trạng thái</label>
          <select id="review-state" value={state} onChange={(e) => setState(e.target.value as State)}>
            {Object.entries(REVIEW_STATES).map(([value, [text]]) => <option key={value} value={value}>{text}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="review-reason">Lý do</label>
          <select id="review-reason" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="">Tất cả</option>
            {Object.entries(REVIEW_REASONS).filter(([code]) => !code.startsWith('CANDIDATE_'))
              .map(([code, text]) => <option key={code} value={code}>{text}</option>)}
          </select>
        </div>
        {version && <p className="muted">Đang lọc theo một phiên bản. <Link href="/review">Bỏ lọc</Link></p>}
      </div>
      {items.error && items.items.length === 0 ? <ErrorState error={items.error} retry={items.reload} />
        : items.loading ? <Loading rows={5} />
        : items.items.length === 0 ? (
          <Empty title={state === 'open' ? 'Không còn trang nào cần duyệt' : 'Không có mục nào'}>
            {state === 'open' ? 'Mọi trang đã được chấp nhận hoặc xử lý.' : 'Đổi bộ lọc để xem mục khác.'}
          </Empty>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Mục cần duyệt</caption>
                <thead>
                  <tr><th scope="col">Tạo lúc</th><th scope="col">Sách</th><th scope="col" className="num">Trang</th>
                    <th scope="col">Lý do</th><th scope="col">Mức</th><th scope="col">Trạng thái</th>
                    <th scope="col"><span className="visually-hidden">Mở</span></th></tr>
                </thead>
                <tbody>
                  {items.items.map((item) => (
                    <tr key={item.id}>
                      <td className="nowrap">{formatDateTime(item.created_at)}</td>
                      <td>{item.book_version_id
                        ? <Link href={`/versions/${item.book_version_id}`}>{item.book_title ?? 'Sách'}</Link> : '—'}</td>
                      <td className="num">{item.physical_page_number ?? '—'}</td>
                      <td>{REVIEW_REASONS[item.reason_code] ?? item.reason_code}</td>
                      <td><StateBadge labels={SEVERITIES} value={item.severity} /></td>
                      <td><StateBadge labels={REVIEW_STATES} value={item.state} /></td>
                      <td>{item.page_revision_id && (
                        <Link href={`/pages/${item.page_revision_id}?item=${item.id}`}>
                          Duyệt trang {item.physical_page_number}
                        </Link>
                      )}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {items.hasMore && (
              <div className="pager">
                <button type="button" className="button button-secondary" onClick={items.loadMore}
                        disabled={items.loadingMore}>{items.loadingMore ? 'Đang tải…' : 'Tải thêm'}</button>
              </div>
            )}
          </>
        )}
    </>
  )
}

export default function ReviewPage() {
  const { can } = useSession()
  return (
    <>
      <title>Duyệt nguồn · Kho Bát Tự</title>
      <PageHeader title="Duyệt nguồn"
                  description="Trang OCR kém, thiếu chữ, sai thứ tự đọc hoặc lệch hàng Can/Chi: so ảnh với text rồi sửa, chấp nhận hoặc loại trừ." />
      {can('library:review')
        ? <Suspense fallback={<Loading rows={5} />}><Queue /></Suspense>
        : <Forbidden what="hàng đợi duyệt" />}
    </>
  )
}
