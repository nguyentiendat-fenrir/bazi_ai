'use client'
// One book version: generation and coverage, pages, jobs; process, publish, withdraw.
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useCallback, useState } from 'react'

import { api, call, idempotencyKey, type Schemas } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { JobRow } from '@/components/JobRow'
import { Empty, ErrorState, Facts, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import {
  GENERATION_STATES, PAGE_STATES, RIGHTS, VERSION_STATUS, formatBytes, formatDateTime, percent, shortId,
} from '@/lib/format'
import { usePagedList, useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Generation = Schemas['GenerationDTO']

function PublishDialog({ generation, open, onClose, onDone }: {
  generation: Generation, open: boolean, onClose(): void, onDone(message: string): void,
}) {
  const c = generation.coverage
  const partial = c.review_required + c.excluded + c.missing > 0
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [key] = useState(idempotencyKey)

  const publish = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await call(api.POST('/api/v1/generations/{generation_id}/publish', {
        params: { path: { generation_id: generation.id } },
        body: { allow_partial: partial, ack_excluded_ranges: partial ? c.excluded_ranges : [], activate: true },
        headers: { 'Idempotency-Key': key },
      }))
      onDone(result.data.activated
        ? `Đã publish: release ${shortId(result.data.release.id)} đang được dùng để tra cứu.`
        : `Đã tạo release ${shortId(result.data.release.id)} (chưa kích hoạt).`)
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Publish vào kho tra cứu"
            footer={<>
              <button type="button" className="button button-ghost" onClick={onClose}>Để sau</button>
              <button type="button" className="button" disabled={busy || (partial && !acknowledged)}
                      onClick={() => void publish()}>{busy ? 'Đang publish…' : 'Publish'}</button>
            </>}>
      <p>{c.accepted}/{c.total} trang đạt ({percent(c.accepted, c.total)}). Release mới gồm phiên bản
        này cùng các sách đang có; người đọc thấy ngay sau khi kích hoạt.</p>
      {partial && (
        <>
          <Notice tone="warning">
            Các trang sau sẽ <strong>không</strong> có trong tra cứu: {c.excluded_ranges.join(', ')}
            {' '}({c.review_required} cần duyệt, {c.excluded} loại trừ, {c.missing} thiếu).
          </Notice>
          <label className="checkbox">
            <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
            <span>Tôi đã xem và chấp nhận publish thiếu các trang {c.excluded_ranges.join(', ')}</span>
          </label>
        </>
      )}
      <FormError error={error} />
    </Dialog>
  )
}

function WithdrawDialog({ versionId, title, open, onClose, onDone }: {
  versionId: string, title: string, open: boolean, onClose(): void, onDone(): void,
}) {
  const [typed, setTyped] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const ready = typed.trim() === title.trim() && reason.trim().length >= 3

  const withdraw = async () => {
    setBusy(true)
    setError(null)
    try {
      await call(api.POST('/api/v1/book-versions/{version_id}/withdraw', {
        params: { path: { version_id: versionId } }, body: { reason: reason.trim() } }))
      onDone()
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Thu hồi phiên bản sách"
            footer={<>
              <button type="button" className="button button-ghost" onClick={onClose}>Không thu hồi</button>
              <button type="button" className="button button-danger" disabled={!ready || busy}
                      onClick={() => void withdraw()}>{busy ? 'Đang thu hồi…' : 'Thu hồi ngay'}</button>
            </>}>
      <p>Phiên bản này bị gỡ khỏi tra cứu ngay lập tức (release mới không chứa nó); tệp gốc và lịch sử
        được giữ. Không hoàn tác bằng nút; muốn dùng lại phải tải lên và duyệt lại.</p>
      <div className="field">
        <label htmlFor="withdraw-title">Gõ đúng tên sách để xác nhận: <strong>{title}</strong></label>
        <input id="withdraw-title" type="text" value={typed} onChange={(e) => setTyped(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="withdraw-reason">Lý do (ghi vào nhật ký kiểm toán)</label>
        <textarea id="withdraw-reason" rows={2} value={reason} maxLength={500}
                  onChange={(e) => setReason(e.target.value)} />
      </div>
      <FormError error={error} />
    </Dialog>
  )
}

function PagesTable({ versionId }: { versionId: string }) {
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/book-versions/{version_id}/pages', {
    params: { path: { version_id: versionId }, query: { limit: 100, cursor } } })), [versionId])
  const pages = usePagedList(`version:${versionId}:pages`, load)
  if (pages.error && pages.items.length === 0) return <ErrorState error={pages.error} retry={pages.reload} />
  if (pages.loading) return <Loading rows={4} />
  if (pages.items.length === 0) return <p className="muted">Chưa có trang: phiên bản chưa được xử lý.</p>
  return (
    <>
      <div className="table-wrap">
        <table>
          <caption className="visually-hidden">Các trang của phiên bản</caption>
          <thead>
            <tr><th scope="col" className="num">Trang</th><th scope="col">Số in</th><th scope="col">Loại</th>
              <th scope="col">Trạng thái</th><th scope="col" className="num">Bản sửa</th>
              <th scope="col"><span className="visually-hidden">Mở</span></th></tr>
          </thead>
          <tbody>
            {pages.items.map((p) => (
              <tr key={p.page_id}>
                <td className="num">{p.physical_page_number}</td>
                <td>{p.printed_page_label ?? '—'}</td>
                <td>{p.page_kind === 'pdf_page' ? 'PDF' : p.page_kind === 'docx_rendered_page' ? 'DOCX (bản dựng)' : 'DOCX (mục)'}</td>
                <td><StateBadge labels={PAGE_STATES} value={p.state} /></td>
                <td className="num">{p.revision_no}</td>
                <td><Link href={`/pages/${p.revision_id}`}>Xem trang {p.physical_page_number}</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages.hasMore && (
        <div className="pager">
          <button type="button" className="button button-secondary" onClick={pages.loadMore}
                  disabled={pages.loadingMore}>{pages.loadingMore ? 'Đang tải…' : 'Tải thêm trang'}</button>
        </div>
      )}
    </>
  )
}

export default function VersionPage() {
  const { versionId } = useParams<{ versionId: string }>()
  const router = useRouter()
  const { can } = useSession()
  const reviewer = can('library:review')
  const version = useQuery(`version:${versionId}`, () =>
    call(api.GET('/api/v1/book-versions/{version_id}', { params: { path: { version_id: versionId } } })))
  const v = version.data?.data
  const book = useQuery(v ? `book:${v.book_id}` : null, () =>
    call(api.GET('/api/v1/books/{book_id}', { params: { path: { book_id: v!.book_id } } })))
  const generationId = v?.current_generation_id ?? null
  const generation = useQuery(reviewer && generationId ? `generation:${generationId}` : null, () =>
    call(api.GET('/api/v1/generations/{generation_id}', { params: { path: { generation_id: generationId! } } })),
    { pollMs: 4000 })
  const jobs = useQuery(reviewer ? `version:${versionId}:jobs` : null, () =>
    call(api.GET('/api/v1/jobs', { params: { query: { book_version_id: versionId, limit: 5 } } })), { pollMs: 4000 })
  const [dialog, setDialog] = useState<'publish' | 'withdraw' | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<unknown>(null)
  const [processKey] = useState(idempotencyKey)

  if (version.error) {
    return <><PageHeader title="Phiên bản sách" back={{ href: '/books', label: 'Thư viện sách' }} />
      <ErrorState error={version.error} retry={version.reload} /></>
  }
  if (version.loading || !v) return <Loading rows={6} />
  const title = book.data?.data.title ?? 'Sách'
  const g = generation.data?.data
  const withdrawn = v.status === 'withdrawn'

  const process = async () => {
    setActionError(null)
    try {
      const job = await call(api.POST('/api/v1/book-versions/{version_id}/process', {
        params: { path: { version_id: versionId } }, body: { scope: 'full' },
        headers: { 'Idempotency-Key': processKey } }))
      router.push(`/jobs/${job.data.id}`)
    } catch (caught) {
      setActionError(caught)
    }
  }

  return (
    <>
      <title>{`${title} (${v.edition_label}) · Kho Bát Tự`}</title>
      <PageHeader
        title={<>{title} <span className="muted">· {v.edition_label}</span> <StateBadge labels={VERSION_STATUS} value={v.status} /></>}
        back={{ href: `/books/${v.book_id}`, label: title }}
        actions={reviewer && !withdrawn && <>
          {g?.state === 'ready' && <button type="button" className="button" onClick={() => setDialog('publish')}>Publish…</button>}
          <button type="button" className="button button-secondary" onClick={() => void process()}>Xử lý lại từ đầu</button>
          <button type="button" className="button button-ghost" onClick={() => setDialog('withdraw')}>Thu hồi…</button>
        </>} />
      {message && <Notice tone="ok">{message}</Notice>}
      <FormError error={actionError} />
      <section className="panel" aria-label="Thông tin phiên bản">
        <Facts items={[
          ['Quyền', RIGHTS[v.rights_status] ?? v.rights_status],
          ['Gửi xử lý ngoài', v.external_processing_allowed ? 'Cho phép' : 'Không'],
          ['Định dạng', v.mime === 'application/pdf' ? 'PDF' : 'DOCX'],
          ['Kích thước', formatBytes(v.size_bytes)],
          ['SHA-256', <code key="sha" title={v.sha256}>{shortId(v.sha256, 16)}</code>],
          ['Trang đạt', v.coverage.total ? `${v.coverage.accepted}/${v.coverage.total}` : 'Chưa xử lý'],
        ]} />
      </section>
      {reviewer && (
        <section className="panel" aria-labelledby="generation-heading">
          <h2 id="generation-heading">Bản dựng hiện tại</h2>
          {!generationId ? (
            <p className="muted">Chưa có bản dựng. Dùng “Xử lý lại từ đầu” hoặc tải lên với một pipeline profile.</p>
          ) : generation.error ? <ErrorState error={generation.error} retry={generation.reload} />
            : !g ? <Loading rows={2} /> : (
              <>
                <Facts items={[
                  ['Trạng thái', <StateBadge key="s" labels={GENERATION_STATES} value={g.state} />],
                  ['Trong release đang dùng', g.in_active_release ? 'Có' : 'Không'],
                  ['Trang', `${g.coverage.accepted} đạt · ${g.coverage.review_required} cần duyệt · ${g.coverage.excluded} loại trừ · ${g.coverage.missing} thiếu / ${g.coverage.total}`],
                  ['Trang ngoài tra cứu', g.coverage.excluded_ranges.length ? g.coverage.excluded_ranges.join(', ') : 'Không'],
                  ['Mục duyệt đang mở', Object.values(g.open_review_items).reduce((a, b) => a + Number(b), 0) || 'Không'],
                  ['Job', g.job ? <Link key="j" href={`/jobs/${g.job.id}`}>{shortId(g.job.id)}</Link> : '—'],
                  ['Tạo lúc', formatDateTime(g.created_at)],
                ]} />
                {Object.keys(g.open_review_items).length > 0 && (
                  <p><Link href={`/review?version=${versionId}`}>Mở hàng đợi duyệt của phiên bản này</Link></p>
                )}
                {g.state === 'building' && <p className="muted small">Đang dựng; trang này tự cập nhật.</p>}
              </>
            )}
        </section>
      )}
      <section className="panel" aria-labelledby="pages-heading">
        <h2 id="pages-heading">Trang</h2>
        <PagesTable versionId={versionId} />
      </section>
      {reviewer && (
        <section className="panel" aria-labelledby="version-jobs-heading">
          <div className="panel-head">
            <h2 id="version-jobs-heading">Jobs gần đây</h2>
            <Link href={`/jobs?version=${versionId}`}>Tất cả jobs của phiên bản</Link>
          </div>
          {jobs.error ? <ErrorState error={jobs.error} retry={jobs.reload} />
            : !jobs.data ? <Loading rows={2} />
            : jobs.data.data.length === 0 ? <Empty title="Chưa có job" />
            : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th scope="col">Tạo lúc</th><th scope="col">Sách</th><th scope="col">Trạng thái</th>
                    <th scope="col">Bước</th><th scope="col">Lỗi</th><th scope="col"><span className="visually-hidden">Mở</span></th></tr></thead>
                  <tbody>{jobs.data.data.map((job) => <JobRow key={job.id} job={job} />)}</tbody>
                </table>
              </div>
            )}
        </section>
      )}
      {g && (
        <PublishDialog generation={g} open={dialog === 'publish'} onClose={() => setDialog(null)}
                       onDone={(text) => { setDialog(null); setMessage(text); generation.reload() }} />
      )}
      <WithdrawDialog versionId={versionId} title={title} open={dialog === 'withdraw'} onClose={() => setDialog(null)}
                      onDone={() => { setDialog(null); setMessage('Đã thu hồi phiên bản khỏi tra cứu.'); version.reload() }} />
    </>
  )
}
