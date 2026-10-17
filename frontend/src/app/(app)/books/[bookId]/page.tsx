'use client'
import { useParams } from 'next/navigation'

import { api, call } from '@/api/client'
import { Empty, ErrorState, Facts, Loading, PageHeader, StateBadge } from '@/components/ui'
import { authorLine } from '@/lib/books'
import { RIGHTS, VERSION_STATUS, formatBytes, percent, shortId } from '@/lib/format'
import { useQuery } from '@/lib/query'

export default function BookPage() {
  const { bookId } = useParams<{ bookId: string }>()
  const book = useQuery(`book:${bookId}`, () =>
    call(api.GET('/api/v1/books/{book_id}', { params: { path: { book_id: bookId } } })))
  const versions = useQuery(`book:${bookId}:versions`, () =>
    call(api.GET('/api/v1/books/{book_id}/versions', { params: { path: { book_id: bookId } } })))

  if (book.error) {
    return (
      <>
        <PageHeader title="Sách" back={{ href: '/books', label: 'Thư viện sách' }} />
        <ErrorState error={book.error} retry={book.reload} />
      </>
    )
  }
  if (book.loading || !book.data) return <Loading rows={6} />
  const b = book.data.data
  const coverage = b.active_coverage

  return (
    <>
      <title>{`${b.title} · Kho Bát Tự`}</title>
      <PageHeader title={b.title} back={{ href: '/books', label: 'Thư viện sách' }}
                  description={authorLine(b)} />
      <section className="panel" aria-label="Thông tin sách">
        <Facts items={[
          ['Ngôn ngữ', b.language],
          ['Số phiên bản', String(b.versions_count)],
          ['Trong kho tra cứu', coverage
            ? `${coverage.accepted}/${coverage.total} trang đạt (${percent(coverage.accepted, coverage.total)})`
            : 'Chưa publish'],
          ['Mô tả', b.description || '—'],
        ]} />
      </section>
      <section className="panel" aria-labelledby="versions-heading">
        <h2 id="versions-heading">Phiên bản</h2>
        {versions.error ? <ErrorState error={versions.error} retry={versions.reload} />
          : versions.loading || !versions.data ? <Loading rows={3} />
          : versions.data.data.length === 0 ? (
            <Empty title="Chưa có phiên bản">Sách này chưa có tệp nguồn nào được tải lên.</Empty>
          ) : (
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Các phiên bản của sách</caption>
                <thead>
                  <tr>
                    <th scope="col">#</th>
                    <th scope="col">Ấn bản</th>
                    <th scope="col">Trạng thái</th>
                    <th scope="col">Quyền</th>
                    <th scope="col">Gửi xử lý ngoài</th>
                    <th scope="col">Trang (đạt/tổng)</th>
                    <th scope="col" className="num">Kích thước</th>
                    <th scope="col">SHA-256</th>
                  </tr>
                </thead>
                <tbody>
                  {versions.data.data.map((v) => (
                    <tr key={v.id}>
                      <td>{v.version_no}</td>
                      <td>{v.edition_label}</td>
                      <td><StateBadge labels={VERSION_STATUS} value={v.status} /></td>
                      <td>{RIGHTS[v.rights_status] ?? v.rights_status}</td>
                      <td>{v.external_processing_allowed ? 'Cho phép' : 'Không'}</td>
                      <td>
                        {v.coverage.total ? `${v.coverage.accepted}/${v.coverage.total}` : 'Chưa xử lý'}
                        {v.coverage.excluded ? <span className="muted small"> · {v.coverage.excluded} loại trừ</span> : null}
                        {v.coverage.failed ? <span className="muted small"> · {v.coverage.failed} lỗi</span> : null}
                      </td>
                      <td className="num">{formatBytes(v.size_bytes)}</td>
                      <td className="mono" title={v.sha256}>{shortId(v.sha256, 12)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </section>
    </>
  )
}
