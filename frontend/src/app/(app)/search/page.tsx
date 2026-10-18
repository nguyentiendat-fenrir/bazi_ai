'use client'
// Library search for every reader (docs/07, docs/11): passages from the active corpus with
// their book, section, page, author layer and school; the query lives in the URL so a
// search can be shared. Concepts the ontology expanded the query with are shown.
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { Badge, Empty, ErrorState, Loading, Notice, PageHeader } from '@/components/ui'
import { useQuery } from '@/lib/query'

type Hit = Schemas['Hit']

const SPEAKERS: Record<string, string> = {
  original_author: 'nguyên tác', commentator: 'bình chú', translator: 'người dịch', editor: 'biên tập', unknown: 'chưa rõ lớp',
}
const STATUS: Record<string, string> = {
  empty_corpus: 'Kho tra cứu chưa có sách nào được publish.',
  empty_filters: 'Không có sách nào khớp bộ lọc đã chọn (hoặc bạn chưa được chia sẻ sách đó).',
  no_match: 'Không tìm thấy đoạn nào khớp.',
}

function Passage({ hit }: { hit: Hit }) {
  const [open, setOpen] = useState(false)
  const span = hit.spans[0]
  const long = hit.text.length > 600
  return (
    <li className="passage">
      <div className="passage-head">
        <strong>«{hit.book_title}»</strong>
        {hit.section_title && <span className="muted">· {hit.section_title}</span>}
        <span className="muted">· trang {hit.pages.join(', ')}</span>
        <Badge>{SPEAKERS[hit.speaker_layer] ?? hit.speaker_layer}</Badge>
        {hit.school_key && <Badge tone="info">{hit.school_key}</Badge>}
      </div>
      <p className="passage-text" lang="vi">{open || !long ? hit.text : `${hit.text.slice(0, 600)}…`}</p>
      <div className="actions">
        {long && <button type="button" className="button button-ghost button-small" onClick={() => setOpen(!open)}>{open ? 'Thu gọn' : 'Xem hết'}</button>}
        {span && (
          <Link className="button button-secondary button-small"
                href={`/pages/${span.page_revision_id}?from=${span.start_offset}&to=${hit.spans.at(-1)!.end_offset}`}>Mở trang sách</Link>
        )}
      </div>
    </li>
  )
}

function SearchScreen() {
  const router = useRouter()
  const params = useSearchParams()
  const q = params.get('q') ?? ''
  const schoolParam = params.get('school') ?? ''
  const bookParam = params.get('book') ?? ''
  const [input, setInput] = useState(q)
  const [school, setSchool] = useState(schoolParam)
  const [book, setBook] = useState(bookParam)
  useEffect(() => { setInput(q); setSchool(schoolParam); setBook(bookParam) }, [q, schoolParam, bookParam])
  const schools = useQuery('search:schools', () => call(api.GET('/api/v1/schools')))
  const books = useQuery('search:books', () => call(api.GET('/api/v1/books', { params: { query: { limit: 100 } } })))
  const results = useQuery(q ? `search:${q}:${schoolParam}:${bookParam}` : null, () => call(api.POST('/api/v1/search', { body: {
    query: q, top_k: 20, rerank: true, pack: false, mode: 'research',
    school_ids: schoolParam ? [schoolParam] : [], book_ids: bookParam ? [bookParam] : [],
    book_version_ids: [], topic_ids: [] } })))

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const next = new URLSearchParams()
    if (input.trim()) next.set('q', input.trim())
    if (school) next.set('school', school)
    if (book) next.set('book', book)
    router.push(`/search?${next.toString()}`)
  }

  const data = results.data?.data
  return (
    <>
      <PageHeader title="Tra cứu sách" description="Tìm đoạn sách theo nội dung, có dấu hay không dấu; mỗi kết quả mở được đúng trang." />
      <form className="toolbar" role="search" onSubmit={submit}>
        <div className="field grow">
          <label htmlFor="search-q">Nội dung cần tìm</label>
          <input id="search-q" type="search" value={input} maxLength={500} placeholder="vd. thực thần sinh tài"
                 onChange={(e) => setInput(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="search-school">Trường phái</label>
          <select id="search-school" value={school} onChange={(e) => setSchool(e.target.value)}>
            <option value="">Tất cả</option>
            {schools.data?.data.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="search-book">Sách</label>
          <select id="search-book" value={book} onChange={(e) => setBook(e.target.value)}>
            <option value="">Tất cả</option>
            {books.data?.data.map((b) => <option key={b.id} value={b.id}>{b.title}</option>)}
          </select>
        </div>
        <button type="submit" className="button" disabled={!input.trim()}>Tìm</button>
      </form>
      {!q ? (
        <Empty title="Nhập nội dung để tìm">Kết quả lấy từ các sách đã publish mà bạn được xem, theo bản kho tra cứu đang dùng.</Empty>
      ) : results.error ? <ErrorState error={results.error} retry={results.reload} />
        : !data ? <Loading rows={4} />
        : (
          <>
            {data.degraded.length > 0 && <Notice tone="warning">Một phần tra cứu đang tạm ngưng ({data.degraded.join(', ')}); kết quả có thể kém hơn bình thường.</Notice>}
            {data.query.expansions.length > 0 && (
              <p className="muted small">Tìm cả theo khái niệm: {data.query.expansions.map((e) => `${e.concept} (${e.school_key}): ${e.variants.join(', ')}`).join('; ')}</p>
            )}
            {data.status !== 'ok' ? <Empty title="Không có kết quả">{STATUS[data.status] ?? data.status}</Empty> : (
              <>
                <p className="muted small" role="status">{data.hits.length} đoạn · {data.took_ms} ms</p>
                <ol className="passages">{data.hits.map((h) => <Passage key={h.chunk_id} hit={h} />)}</ol>
              </>
            )}
          </>
        )}
    </>
  )
}

export default function SearchPage() {
  return (
    <>
      <title>Tra cứu · Kho Bát Tự</title>
      <Suspense fallback={<Loading rows={4} />}><SearchScreen /></Suspense>
    </>
  )
}
