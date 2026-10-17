'use client'
import Link from 'next/link'

import { api, call } from '@/api/client'
import { Empty, ErrorState, Loading, PageHeader } from '@/components/ui'
import { formatDateTime, formatNumber, shortId } from '@/lib/format'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

/** "12" when the page holds everything, "100+" when the API says there is more. */
function count(items: unknown[], more: boolean | undefined): string {
  return more ? `${formatNumber(items.length)}+` : formatNumber(items.length)
}

function LibraryPanel() {
  const books = useQuery('dashboard:books', () =>
    call(api.GET('/api/v1/books', { params: { query: { limit: 6 } } })))
  return (
    <section className="panel" aria-labelledby="library-heading">
      <div className="panel-head">
        <h2 id="library-heading">Thư viện</h2>
        <Link href="/books">Xem tất cả</Link>
      </div>
      {books.error ? <ErrorState error={books.error} retry={books.reload} />
        : books.loading || !books.data ? <Loading rows={3} />
        : books.data.data.length === 0 ? (
          <Empty title="Chưa có sách nào">
            Kho chưa có sách bạn được xem. Người duyệt tải sách lên rồi publish để tra cứu.
          </Empty>
        ) : (
          <ul className="plain-list">
            {books.data.data.map((book) => (
              <li key={book.id}>
                <Link href={`/books/${book.id}`}>{book.title}</Link>
                <span className="muted small">
                  {' · '}{book.versions_count} phiên bản
                  {book.active_coverage ? ' · đang trong kho tra cứu' : ' · chưa publish'}
                </span>
              </li>
            ))}
          </ul>
        )}
    </section>
  )
}

function OperationsPanels() {
  const jobs = useQuery('dashboard:jobs', async () => {
    const [running, queued] = await Promise.all([
      call(api.GET('/api/v1/jobs', { params: { query: { state: 'running', limit: 100 } } })),
      call(api.GET('/api/v1/jobs', { params: { query: { state: 'queued', limit: 100 } } })),
    ])
    return { running, queued }
  }, { pollMs: 10_000 })
  const reviews = useQuery('dashboard:reviews', () =>
    call(api.GET('/api/v1/review-items', { params: { query: { state: 'open', limit: 100 } } })))
  const releases = useQuery('dashboard:releases', () =>
    call(api.GET('/api/v1/corpus-releases', { params: { query: { limit: 1 } } })))

  const active = releases.data?.data.active
  const latest = releases.data?.data.releases.find((r) => r.id === active?.release_id)
  return (
    <div className="grid">
      <section className="panel" aria-labelledby="jobs-heading">
        <h2 id="jobs-heading">Jobs xử lý sách</h2>
        {jobs.error ? <ErrorState error={jobs.error} retry={jobs.reload} />
          : jobs.loading || !jobs.data ? <Loading rows={2} />
          : (
            <p>
              <span className="stat">{count(jobs.data.running.data, jobs.data.running.page?.has_more)}</span>
              {' '}đang chạy ·{' '}
              <span className="stat">{count(jobs.data.queued.data, jobs.data.queued.page?.has_more)}</span>
              {' '}đang chờ
            </p>
          )}
      </section>
      <section className="panel" aria-labelledby="reviews-heading">
        <h2 id="reviews-heading">Mục cần duyệt</h2>
        {reviews.error ? <ErrorState error={reviews.error} retry={reviews.reload} />
          : reviews.loading || !reviews.data ? <Loading rows={2} />
          : (
            <p>
              <span className="stat">{count(reviews.data.data, reviews.data.page?.has_more)}</span>
              {' '}mục đang mở (OCR, nguồn đã sửa, ứng viên tri thức)
            </p>
          )}
      </section>
      <section className="panel" aria-labelledby="release-heading">
        <h2 id="release-heading">Kho tra cứu đang dùng</h2>
        {releases.error ? <ErrorState error={releases.error} retry={releases.reload} />
          : releases.loading || !releases.data ? <Loading rows={2} />
          : !active ? (
            <p className="muted">Chưa có release nào: tra cứu đang trống cho đến khi publish sách đầu tiên.</p>
          ) : (
            <p>
              Release <code>{shortId(active.release_id)}</code>
              {latest && <> · {formatNumber(latest.members_count)} phiên bản sách · tạo {formatDateTime(latest.created_at)}</>}
              <br /><span className="muted small">Epoch hiển thị {active.visibility_epoch}</span>
            </p>
          )}
      </section>
    </div>
  )
}

export default function DashboardPage() {
  const { user, can } = useSession()
  return (
    <>
      <title>Tổng quan · Kho Bát Tự</title>
      <PageHeader title="Tổng quan" description={`Xin chào ${user?.email ?? ''}`} />
      {can('library:review') && <OperationsPanels />}
      <LibraryPanel />
    </>
  )
}
