'use client'
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { Empty, ErrorState, Loading, PageHeader } from '@/components/ui'
import { authorLine } from '@/lib/books'
import { percent } from '@/lib/format'
import { usePagedList } from '@/lib/query'

type Book = Schemas['BookDTO']

function Coverage({ book }: { book: Book }) {
  const c = book.active_coverage
  if (!c) return <span className="muted">Chưa publish</span>
  return (
    <span title={`${c.accepted}/${c.total} trang đạt; ${c.review_required} cần duyệt; ${c.excluded} loại trừ`}>
      {c.accepted}/{c.total} trang ({percent(c.accepted, c.total)})
    </span>
  )
}

export default function BooksPage() {
  const [input, setInput] = useState('')
  const [term, setTerm] = useState('')

  // Search as the user types, without a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setTerm(input.trim()), 300)
    return () => clearTimeout(timer)
  }, [input])

  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/books', {
    params: { query: { q: term || undefined, limit: 50, cursor } },
  })), [term])
  const books = usePagedList(`books:${term}`, load)

  return (
    <>
      <title>Thư viện sách · Kho Bát Tự</title>
      <PageHeader title="Thư viện sách"
                  description="Sách bạn được xem; tìm theo tên không cần gõ dấu." />
      <div className="toolbar">
        <div className="field grow">
          <label htmlFor="book-search">Tìm sách</label>
          <input id="book-search" type="search" value={input} placeholder="ví dụ: tu binh chan thuyen"
                 onChange={(e) => setInput(e.target.value)} />
        </div>
      </div>
      {books.error && books.items.length === 0 ? <ErrorState error={books.error} retry={books.reload} />
        : books.loading ? <Loading rows={5} />
        : books.items.length === 0 ? (
          term ? (
            <Empty title="Không có sách khớp">Không tìm thấy sách có tên chứa “{term}”.</Empty>
          ) : (
            <Empty title="Chưa có sách nào">
              Kho chưa có sách bạn được xem. Sách mới mặc định riêng tư cho tới khi được cấp quyền.
            </Empty>
          )
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Danh sách sách</caption>
                <thead>
                  <tr>
                    <th scope="col">Tên sách</th>
                    <th scope="col">Tác giả</th>
                    <th scope="col">Ngôn ngữ</th>
                    <th scope="col" className="num">Phiên bản</th>
                    <th scope="col">Trong kho tra cứu</th>
                  </tr>
                </thead>
                <tbody>
                  {books.items.map((book) => (
                    <tr key={book.id}>
                      <td><Link href={`/books/${book.id}`}>{book.title}</Link></td>
                      <td>{authorLine(book)}</td>
                      <td>{book.language}</td>
                      <td className="num">{book.versions_count}</td>
                      <td><Coverage book={book} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {books.error ? <ErrorState error={books.error} retry={books.loadMore} /> : null}
            {books.hasMore && (
              <div className="pager">
                <button type="button" className="button button-secondary" onClick={books.loadMore}
                        disabled={books.loadingMore}>
                  {books.loadingMore ? 'Đang tải…' : 'Tải thêm'}
                </button>
              </div>
            )}
          </>
        )}
    </>
  )
}
