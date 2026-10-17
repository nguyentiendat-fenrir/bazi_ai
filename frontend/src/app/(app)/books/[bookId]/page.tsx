'use client'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, ifMatch, type Schemas } from '@/api/client'
import { ApiError } from '@/api/problem'
import { Empty, ErrorState, Facts, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { authorLine } from '@/lib/books'
import { RIGHTS, VERSION_STATUS, formatBytes, percent, shortId } from '@/lib/format'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Book = Schemas['BookDTO']
interface Draft { title: string, language: string, description: string }

/** Metadata form; a 412 keeps the draft and shows what the other reviewer saved. */
function EditBook({ book, onSaved, onCancel }: { book: Book, onSaved(book: Book): void, onCancel(): void }) {
  const [draft, setDraft] = useState<Draft>({
    title: book.title, language: book.language, description: book.description ?? '' })
  const [base, setBase] = useState(book)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const saved = await call(api.PATCH('/api/v1/books/{book_id}', {
        params: { path: { book_id: book.id }, header: { 'If-Match': ifMatch(base.revision) } },
        body: { title: draft.title.trim(), language: draft.language, description: draft.description.trim() },
      }))
      onSaved(saved.data)
    } catch (caught) {
      setError(caught)
      if (caught instanceof ApiError && caught.code === 'REVISION_MISMATCH') {
        try {
          setBase((await call(api.GET('/api/v1/books/{book_id}', { params: { path: { book_id: book.id } } }))).data)
        } catch {
          // the error above is already shown
        }
      }
    } finally {
      setBusy(false)
    }
  }

  const conflict = base.revision !== book.revision
  return (
    <form className="panel" onSubmit={submit} aria-labelledby="edit-heading">
      <h2 id="edit-heading">Sửa thông tin sách</h2>
      {conflict && (
        <Notice tone="warning">
          Người khác vừa lưu bản {base.revision}: tên “{base.title}”, ngôn ngữ {base.language}. Bản nháp của bạn vẫn
          giữ nguyên bên dưới; lưu lần nữa sẽ ghi lên bản mới đó.
        </Notice>
      )}
      <div className="form-grid">
        <div className="field">
          <label htmlFor="book-title">Tên sách</label>
          <input id="book-title" type="text" value={draft.title} maxLength={500} required
                 onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="book-language">Ngôn ngữ</label>
          <select id="book-language" value={draft.language} onChange={(e) => setDraft({ ...draft, language: e.target.value })}>
            {Array.from(new Set(['vi', 'zh', 'en', draft.language])).map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="book-description">Mô tả</label>
        <textarea id="book-description" rows={3} maxLength={5000} value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
      </div>
      {!(error instanceof ApiError && error.code === 'REVISION_MISMATCH') && <FormError error={error} />}
      <div className="actions">
        <button type="submit" className="button" disabled={busy || !draft.title.trim()}>{busy ? 'Đang lưu…' : 'Lưu'}</button>
        <button type="button" className="button button-ghost" onClick={onCancel}>Hủy</button>
      </div>
    </form>
  )
}

export default function BookPage() {
  const { bookId } = useParams<{ bookId: string }>()
  const { can } = useSession()
  const reviewer = can('library:review')
  const book = useQuery(`book:${bookId}`, () =>
    call(api.GET('/api/v1/books/{book_id}', { params: { path: { book_id: bookId } } })))
  const versions = useQuery(`book:${bookId}:versions`, () =>
    call(api.GET('/api/v1/books/{book_id}/versions', { params: { path: { book_id: bookId } } })))
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)

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
                  description={authorLine(b)}
                  actions={reviewer && <>
                    <Link className="button" href={`/books/upload?book=${b.id}`}>Tải phiên bản mới</Link>
                    {!editing && <button type="button" className="button button-secondary"
                                         onClick={() => { setEditing(true); setSaved(false) }}>Sửa thông tin</button>}
                  </>} />
      {saved && <Notice tone="ok">Đã lưu thông tin sách.</Notice>}
      {editing ? (
        <EditBook book={b} onCancel={() => setEditing(false)}
                  onSaved={(next) => { book.replace({ ...book.data!, data: next }); setEditing(false); setSaved(true) }} />
      ) : (
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
      )}
      <section className="panel" aria-labelledby="versions-heading">
        <h2 id="versions-heading">Phiên bản</h2>
        {versions.error ? <ErrorState error={versions.error} retry={versions.reload} />
          : versions.loading || !versions.data ? <Loading rows={3} />
          : versions.data.data.length === 0 ? (
            <Empty title="Chưa có phiên bản"
                   action={reviewer && <Link className="button" href={`/books/upload?book=${b.id}`}>Tải tệp lên</Link>}>
              Sách này chưa có tệp nguồn nào được tải lên.
            </Empty>
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
                      <td><Link href={`/versions/${v.id}`}>{v.edition_label}</Link></td>
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
