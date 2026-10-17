'use client'
// Upload books (docs/11 /books/upload): one batch, each file its own request with its own
// Idempotency-Key, two at a time; one bad file never stops the others.
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, idempotencyKey, reportAuthFailure, type Schemas } from '@/api/client'
import { ApiError, describe } from '@/api/problem'
import { ErrorState, Forbidden, FormError, Loading, Notice, PageHeader } from '@/components/ui'
import { RIGHTS, formatBytes, formatDateTime } from '@/lib/format'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'
import { type UploadOutcome, uploadFile } from '@/lib/upload'

type Profile = Schemas['PipelineProfileDTO']
type Status = 'ready' | 'uploading' | 'accepted' | 'duplicate' | 'rejected' | 'failed'

interface Item {
  id: string
  file: File
  title: string
  key: string
  status: Status
  progress: number
  result?: UploadOutcome
  error?: ApiError
}

const CONCURRENCY = 2
const STATUS_TEXT: Record<Status, string> = {
  ready: 'Chờ tải', uploading: 'Đang tải', accepted: 'Đã nhận', duplicate: 'Trùng tệp đã có',
  rejected: 'Bị từ chối', failed: 'Lỗi kết nối',
}

function titleOf(name: string): string {
  return name.replace(/\.[^.]+$/, '').replace(/[_]+/g, ' ').trim()
}

function profileLabel(p: Profile): string {
  const where = { fixture: 'mô hình thử nghiệm', local: 'mô hình nội bộ', external: 'mô hình bên ngoài' }
  return `${p.name} · ${p.embedding.model_name} (${where[p.embedding.locality]})`
}

function UploadForm() {
  const bookId = useSearchParams().get('book')
  const book = useQuery(bookId ? `upload:book:${bookId}` : null, () =>
    call(api.GET('/api/v1/books/{book_id}', { params: { path: { book_id: bookId! } } })))
  const profiles = useQuery('upload:profiles', () => call(api.GET('/api/v1/pipeline-profiles')))

  const [name, setName] = useState(() => `Tải lên ${formatDateTime(new Date().toISOString())}`)
  const [profileId, setProfileId] = useState<string | null>(null)
  const [rights, setRights] = useState('unknown')
  const [edition, setEdition] = useState('v1')
  const [language, setLanguage] = useState('vi')
  const [external, setExternal] = useState(false)
  const [autoPublish, setAutoPublish] = useState(false)
  const [items, setItems] = useState<Item[]>([])
  const [batchId, setBatchId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<unknown>(null)
  const [summary, setSummary] = useState<Schemas['BatchDTO'] | null>(null)
  const itemsRef = useRef(items)
  itemsRef.current = items

  // Preselect the newest profile whose vector collection is ready.
  useEffect(() => {
    if (profileId === null && profiles.data) {
      setProfileId(profiles.data.data.find((p) => p.embedding.ready)?.id ?? '')
    }
  }, [profiles.data, profileId])

  const profile = useMemo(() => profiles.data?.data.find((p) => p.id === profileId) ?? null,
                          [profiles.data, profileId])
  const locked = batchId !== null

  const update = (id: string, change: Partial<Item>) =>
    setItems((current) => current.map((item) => item.id === id ? { ...item, ...change } : item))

  const addFiles = (files: FileList | null) => {
    if (!files) return
    const added = Array.from(files).map((file) => ({
      id: crypto.randomUUID(), file, title: titleOf(file.name), key: idempotencyKey(),
      status: 'ready' as Status, progress: 0,
    }))
    setItems((current) => [...current, ...added])
  }

  const sendOne = async (batch: string, item: Item) => {
    update(item.id, { status: 'uploading', progress: 0, error: undefined })
    try {
      const result = await uploadFile(item.file, {
        batch_id: batch, rights_status: rights, edition_label: edition, language,
        external_processing_allowed: external,
        ...(bookId ? { book_id: bookId } : { title: item.title.trim() || undefined }),
      }, item.key, (progress) => update(item.id, { progress }))
      update(item.id, { status: result.outcome, progress: 1, result })
    } catch (caught) {
      const error = caught instanceof ApiError ? caught : new ApiError(0, 'NETWORK_ERROR', String(caught))
      reportAuthFailure(error)
      // A rejected request left nothing behind: the next attempt may change the file's
      // details, so it gets a fresh key; after a network error the same key replays.
      const rejected = error.status >= 400 && error.status < 500
      update(item.id, { status: rejected ? 'rejected' : 'failed', error,
                        key: rejected ? idempotencyKey() : item.key })
    }
  }

  const run = async (only?: string) => {
    setBusy(true)
    setFormError(null)
    try {
      let batch = batchId
      if (!batch) {
        const created = await call(api.POST('/api/v1/ingestion-batches', {
          body: { name: name.trim(), pipeline_profile_id: profileId || null, auto_publish: autoPublish },
        }))
        batch = created.data.id
        setBatchId(batch)
      }
      const queue = itemsRef.current.filter((item) =>
        only ? item.id === only : item.status === 'ready' || item.status === 'failed')
      const workers = Array.from({ length: CONCURRENCY }, async () => {
        for (let next = queue.shift(); next; next = queue.shift()) await sendOne(batch!, next)
      })
      await Promise.all(workers)
      setSummary((await call(api.GET('/api/v1/ingestion-batches/{batch_id}', {
        params: { path: { batch_id: batch } } }))).data)
    } catch (caught) {
      setFormError(caught)
    } finally {
      setBusy(false)
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void run()
  }

  if (profiles.error) return <ErrorState error={profiles.error} retry={profiles.reload} />
  if (profiles.loading || (bookId && book.loading)) return <Loading rows={6} />
  if (bookId && book.error) return <ErrorState error={book.error} retry={book.reload} />
  const pending = items.some((i) => i.status === 'ready' || i.status === 'failed')

  return (
    <form onSubmit={submit} noValidate>
      {book.data && <Notice>Thêm phiên bản mới cho sách <strong>{book.data.data.title}</strong>.</Notice>}
      <section className="panel" aria-labelledby="batch-heading">
        <h2 id="batch-heading">Lô tải lên</h2>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="batch-name">Tên lô</label>
            <input id="batch-name" type="text" value={name} disabled={locked} maxLength={200}
                   onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="profile">Cách xử lý</label>
            <select id="profile" value={profileId ?? ''} disabled={locked}
                    onChange={(e) => setProfileId(e.target.value)}>
              <option value="">Chỉ lưu tệp, xử lý sau</option>
              {profiles.data?.data.map((p) => (
                <option key={p.id} value={p.id} disabled={!p.embedding.ready}>
                  {profileLabel(p)}{p.embedding.ready ? '' : ' — chưa sẵn sàng'}
                </option>
              ))}
            </select>
            {profiles.data?.data.length === 0 && (
              <span className="hint">Chưa có pipeline profile; quản trị tạo bằng CLI <code>pipeline-profile</code>.</span>
            )}
          </div>
        </div>
        <label className="checkbox">
          <input type="checkbox" checked={autoPublish} disabled={locked || !profileId}
                 onChange={(e) => setAutoPublish(e.target.checked)} />
          <span>Tự publish khi mọi trang đạt (trang cần duyệt vẫn phải publish thủ công)</span>
        </label>
      </section>

      <section className="panel" aria-labelledby="meta-heading">
        <h2 id="meta-heading">Thông tin áp cho mọi tệp</h2>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="rights">Quyền sử dụng</label>
            <select id="rights" value={rights} disabled={busy} onChange={(e) => setRights(e.target.value)}>
              {Object.entries(RIGHTS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
            <span className="hint">“Hạn chế” không bao giờ được publish.</span>
          </div>
          <div className="field">
            <label htmlFor="edition">Nhãn ấn bản</label>
            <input id="edition" type="text" value={edition} maxLength={200} disabled={busy}
                   onChange={(e) => setEdition(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="language">Ngôn ngữ</label>
            <select id="language" value={language} disabled={busy} onChange={(e) => setLanguage(e.target.value)}>
              <option value="vi">Tiếng Việt (vi)</option>
              <option value="zh">Tiếng Trung (zh)</option>
              <option value="en">Tiếng Anh (en)</option>
            </select>
          </div>
        </div>
        <label className="checkbox">
          <input type="checkbox" checked={external} disabled={busy} onChange={(e) => setExternal(e.target.checked)} />
          <span>Cho phép gửi nội dung sách tới dịch vụ bên ngoài (mặc định: không)</span>
        </label>
        {profile?.embedding.locality === 'external' && !external && (
          <Notice tone="warning">
            Profile này dùng mô hình bên ngoài: tệp không cho phép xử lý ngoài sẽ dừng ở bước vector hóa
            (<code>EXTERNAL_PROCESSING_DENIED</code>).
          </Notice>
        )}
      </section>

      <section className="panel" aria-labelledby="files-heading">
        <div className="panel-head">
          <h2 id="files-heading">Tệp ({items.length})</h2>
          <label className="button button-secondary file-pick">
            Chọn tệp PDF/DOCX
            <input type="file" multiple accept=".pdf,.docx,application/pdf" className="visually-hidden"
                   onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
          </label>
        </div>
        {items.length === 0 ? (
          <p className="muted">Chưa chọn tệp. Có thể chọn nhiều tệp; mỗi tệp thành một phiên bản sách.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Tệp</th>
                  {!bookId && <th scope="col">Tên sách</th>}
                  <th scope="col">Trạng thái</th>
                  <th scope="col">Kết quả</th>
                  <th scope="col"><span className="visually-hidden">Thao tác</span></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} data-file={item.file.name}>
                    <td>
                      <div>{item.file.name}</div>
                      <div className="muted small">{formatBytes(item.file.size)}</div>
                    </td>
                    {!bookId && (
                      <td>
                        <input type="text" aria-label={`Tên sách cho ${item.file.name}`} value={item.title}
                               maxLength={500} disabled={item.status !== 'ready' && item.status !== 'rejected'}
                               onChange={(e) => update(item.id, { title: e.target.value })} />
                      </td>
                    )}
                    <td>
                      <span className={`upload-status upload-${item.status}`}>{STATUS_TEXT[item.status]}</span>
                      {item.status === 'uploading' && (
                        <progress max={1} value={item.progress} aria-label={`Tiến độ ${item.file.name}`} />
                      )}
                    </td>
                    <td>
                      {item.result?.outcome === 'accepted' && (
                        <span>
                          <Link href={`/books/${item.result.book_id}`}>Sách</Link>
                          {item.result.job_id
                            ? <> · <Link href={`/jobs/${item.result.job_id}`}>Theo dõi job</Link></>
                            : item.result.version_id && <> · <Link href={`/versions/${item.result.version_id}`}>Phiên bản (chưa xử lý)</Link></>}
                        </span>
                      )}
                      {item.result?.outcome === 'duplicate' && item.result.duplicate_of && (
                        <Link href={`/versions/${item.result.duplicate_of}`}>Mở phiên bản đã có</Link>
                      )}
                      {item.error && <span className="error-text">{describe(item.error)} <code>{item.error.code}</code></span>}
                    </td>
                    <td className="nowrap">
                      {item.status === 'ready' && !busy && (
                        <button type="button" className="button button-ghost button-small"
                                onClick={() => setItems((current) => current.filter((i) => i.id !== item.id))}>
                          Bỏ
                        </button>
                      )}
                      {(item.status === 'rejected' || item.status === 'failed') && locked && !busy && (
                        <button type="button" className="button button-secondary button-small"
                                onClick={() => void run(item.id)}>
                          Thử lại tệp này
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <FormError error={formError} />
      {summary && (
        <Notice tone={summary.counters.rejected ? 'warning' : 'ok'}>
          Lô “{summary.name}”: {summary.counters.accepted ?? 0} nhận, {summary.counters.duplicate ?? 0} trùng,
          {' '}{summary.counters.rejected ?? 0} bị từ chối.{' '}
          {summary.pipeline_profile_id && <Link href="/jobs">Xem jobs xử lý</Link>}
        </Notice>
      )}
      <div className="actions">
        <button type="submit" className="button" disabled={busy || !pending || !name.trim()}>
          {busy ? 'Đang tải lên…' : locked ? 'Tải các tệp còn lại' : 'Bắt đầu tải lên'}
        </button>
      </div>
    </form>
  )
}

export default function UploadPage() {
  const { can } = useSession()
  return (
    <>
      <title>Tải sách lên · Kho Bát Tự</title>
      <PageHeader title="Tải sách lên" back={{ href: '/books', label: 'Thư viện sách' }}
                  description="PDF hoặc DOCX; tệp gốc được giữ nguyên, trùng nội dung sẽ không tạo bản mới." />
      {can('library:review')
        ? <Suspense fallback={<Loading rows={6} />}><UploadForm /></Suspense>
        : <Forbidden what="trang tải sách lên" />}
    </>
  )
}
