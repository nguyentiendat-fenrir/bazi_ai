'use client'
// Page workspace (docs/11 /review/ocr): page image beside its text blocks; reviewers fix
// blocks as a new revision (If-Match on the latest), and resolve the page's review item.
// A 412 keeps every local edit and rebases it onto the newer revision.
import Link from 'next/link'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'

import { api, call, idempotencyKey, ifMatch, type Schemas } from '@/api/client'
import { ApiError } from '@/api/problem'
import { Dialog } from '@/components/Dialog'
import { Badge, ErrorState, Facts, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { type Edit, diffWords, rebase } from '@/lib/diff'
import { PAGE_STATES, REVIEW_REASONS, REVIEW_STATES, SEVERITIES, formatDateTime, shortId } from '@/lib/format'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Revision = Schemas['PageRevisionDTO']
type Block = Revision['blocks'][number]
type Action = 'accept' | 'exclude' | 'retry' | 'dismiss'

const SPEAKERS: Record<string, string> = {
  original_author: 'Nguyên tác', commentator: 'Bình chú', translator: 'Người dịch', editor: 'Biên tập',
  unknown: 'Chưa rõ',
}
const KINDS: Record<string, string> = {
  paragraph: 'Đoạn', heading: 'Tiêu đề', table: 'Bảng', figure: 'Hình', caption: 'Chú thích',
}
const ROLES: Record<string, string> = { header: 'đầu trang', footer: 'chân trang', folio: 'số trang', toc: 'mục lục' }
const ACTIONS: Record<Action, [string, string]> = {
  accept: ['Chấp nhận trang', 'Trang dùng được như hiện tại (đã đối chiếu với ảnh).'],
  exclude: ['Loại trừ trang', 'Trang không đưa vào tra cứu (bìa, ảnh, trang hỏng); vẫn được giữ trong kho nguồn.'],
  retry: ['Chạy lại OCR', 'Dựng lại trang khi máy chủ đã có OCR hoặc cấu hình đã đổi.'],
  dismiss: ['Bỏ qua mục này', 'Đóng mục duyệt mà không đổi trang.'],
}
const ZOOM = [1, 1.5, 2]

function Diff({ before, after }: { before: string, after: string }) {
  return (
    <p className="diff">
      {diffWords(before, after).map((part, i) => part.kind === 'same' ? <span key={i}>{part.text}</span>
        : part.kind === 'removed' ? <del key={i}>{part.text}</del> : <ins key={i}>{part.text}</ins>)}
    </p>
  )
}

function quality(rev: Revision): [string, string][] {
  const q = rev.quality as Record<string, any>
  const facts: [string, string][] = [['Loại trang', rev.layout.page_class ?? '—']]
  if (q.ocr) facts.push(['OCR', `${q.ocr.engine ?? ''} · tin cậy ${q.ocr.mean_conf ?? '—'} · ${q.ocr.mode === 'page' ? 'cả trang' : 'vùng ảnh'}`])
  if (q.replacement_chars) facts.push(['Ký tự mất', String(q.replacement_chars)])
  if (q.needs_ocr) facts.push(['Cần OCR', 'Có'])
  if (q.correction) facts.push(['Bản sửa', `${q.correction.reason ?? ''}`])
  return facts
}

function ResolvePanel({ itemId, rev, dirty, onResolved }: {
  itemId: string, rev: Revision, dirty: boolean, onResolved(): void,
}) {
  const item = useQuery(`review-item:${itemId}`, () =>
    call(api.GET('/api/v1/review-items/{item_id}', { params: { path: { item_id: itemId } } })))
  const [action, setAction] = useState<Action | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [done, setDone] = useState<Schemas['ReviewResolveResult'] | null>(null)
  const [key, setKey] = useState(idempotencyKey)

  if (item.error) return <ErrorState error={item.error} retry={item.reload} />
  if (!item.data) return <Loading rows={2} />
  const it = item.data.data
  const open = it.state === 'open' || it.state === 'in_progress'

  const resolve = async () => {
    if (!action) return
    setBusy(true)
    setError(null)
    try {
      const result = await call(api.POST('/api/v1/review-items/{item_id}/resolve', {
        params: { path: { item_id: itemId }, header: { 'Idempotency-Key': key } },
        body: { action, reason: reason.trim(), base_revision_id: action === 'dismiss' ? null : rev.latest_revision_id },
      }))
      setDone(result.data)
      setAction(null)
      item.replace({ ...item.data!, data: result.data.item })
      onResolved()
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="item-heading">
      <h2 id="item-heading">Mục duyệt: {REVIEW_REASONS[it.reason_code] ?? it.reason_code}</h2>
      <p>
        <StateBadge labels={SEVERITIES} value={it.severity} /> <StateBadge labels={REVIEW_STATES} value={it.state} />
        <span className="muted small"> · tạo {formatDateTime(it.created_at)}</span>
      </p>
      {done && (
        <Notice tone="ok">
          Đã ghi quyết định.{done.job_id && <> Trang được dựng lại trong <Link href={`/jobs/${done.job_id}`}>job {shortId(done.job_id)}</Link>{done.coalesced ? ' (gộp với job đang chờ)' : ''}.</>}
          {' '}<Link href="/review">Về hàng đợi duyệt</Link>
        </Notice>
      )}
      {open && (
        <>
          {!rev.is_latest && <Notice tone="warning">Đây không phải bản mới nhất của trang; mở bản mới nhất để duyệt.</Notice>}
          {dirty && <Notice tone="warning">Bạn có thay đổi chưa lưu: lưu bản sửa trước khi chấp nhận trang.</Notice>}
          <div className="actions">
            {(Object.keys(ACTIONS) as Action[]).map((a) => (
              <button key={a} type="button" className={`button ${a === 'accept' ? '' : 'button-secondary'}`}
                      disabled={(a !== 'dismiss' && (!rev.is_latest || dirty)) || busy}
                      onClick={() => { setAction(a); setReason(''); setKey(idempotencyKey()) }}>
                {ACTIONS[a][0]}
              </button>
            ))}
          </div>
        </>
      )}
      <Dialog open={action !== null} onClose={() => setAction(null)} title={action ? ACTIONS[action][0] : ''}
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setAction(null)}>Hủy</button>
                <button type="button" className="button" disabled={busy || reason.trim().length < 3}
                        onClick={() => void resolve()}>Xác nhận</button>
              </>}>
        <p>{action && ACTIONS[action][1]}</p>
        <div className="field">
          <label htmlFor="resolve-reason">Lý do (ít nhất 3 ký tự)</label>
          <textarea id="resolve-reason" rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <FormError error={error} />
      </Dialog>
    </section>
  )
}

/** The block's text with the cited part marked; offsets are into the revision text. */
function highlight(text: string, start: number, quoted: { from: number, to: number } | null) {
  if (!quoted) return text
  const from = Math.max(0, quoted.from - start)
  const to = Math.min(text.length, quoted.to - start)
  if (to <= 0 || from >= text.length || to <= from) return text
  return <>{text.slice(0, from)}<mark className="quoted">{text.slice(from, to)}</mark>{text.slice(to)}</>
}

export default function PageWorkspace() {
  const { revisionId } = useParams<{ revisionId: string }>()
  const router = useRouter()
  const { can } = useSession()
  const reviewer = can('library:review')
  const search = useSearchParams()
  const itemId = search.get('item')
  // A citation opens the page with the quoted span (offsets into this revision's text).
  const quoteFrom = Number(search.get('from') ?? NaN)
  const quoteTo = Number(search.get('to') ?? NaN)
  const quoted = Number.isFinite(quoteFrom) && Number.isFinite(quoteTo) && quoteTo > quoteFrom
    ? { from: quoteFrom, to: quoteTo } : null
  const savedNotice = search.get('saved')
  const [rev, setRev] = useState<Revision | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [edits, setEdits] = useState<Record<number, Edit>>({})
  const [conflicts, setConflicts] = useState<number[]>([])
  const [conflictNotice, setConflictNotice] = useState<string | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [scale, setScale] = useState(1.5)
  const [imageError, setImageError] = useState(false)
  const [reason, setReason] = useState('')
  const [preview, setPreview] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<unknown>(null)
  const [saveKey, setSaveKey] = useState(idempotencyKey)
  const [attempt, setAttempt] = useState(0)
  const cards = useRef(new Map<number, HTMLElement>())
  const shown = useRef<string | null>(null)

  // A different revision starts clean; a reload of the same one (after resolving) keeps edits.
  useEffect(() => {
    setEdits({})
    setConflicts([])
    setConflictNotice(null)
    setReason('')
    setSaveKey(idempotencyKey())
    setImageError(false)
  }, [revisionId])

  useEffect(() => {
    let live = true
    // Reloading the same revision (after a decision) keeps it on screen meanwhile.
    if (shown.current !== revisionId) {
      shown.current = revisionId
      setRev(null)
    }
    setLoadError(null)
    call(api.GET('/api/v1/page-revisions/{revision_id}', { params: { path: { revision_id: revisionId } } }))
      .then((body) => { if (live) setRev(body.data) }, (error) => { if (live) setLoadError(error) })
    return () => { live = false }
  }, [revisionId, attempt])

  const version = useQuery(rev ? `version:${rev.book_version_id}` : null, () =>
    call(api.GET('/api/v1/book-versions/{version_id}', { params: { path: { version_id: rev!.book_version_id } } })))
  const bookId = version.data?.data.book_id
  const book = useQuery(bookId ? `book:${bookId}` : null, () =>
    call(api.GET('/api/v1/books/{book_id}', { params: { path: { book_id: bookId! } } })))

  const blocks = useMemo(() => new Map((rev?.blocks ?? []).map((b) => [b.ordinal, b])), [rev])
  const changed = Object.keys(edits).length
  const editable = reviewer && !!rev?.is_latest

  const select = (ordinal: number) => {
    setSelected(ordinal)
    cards.current.get(ordinal)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  // Bring the quoted block into view once the revision is on screen.
  const quotedBlock = quoted && rev
    ? rev.blocks.find((b) => b.start_offset < quoted.to && b.end_offset > quoted.from) ?? null : null
  useEffect(() => {
    if (!quotedBlock) return
    setSelected(quotedBlock.ordinal)
    cards.current.get(quotedBlock.ordinal)?.scrollIntoView({ block: 'center' })
  }, [quotedBlock?.ordinal, rev?.id])  // eslint-disable-line react-hooks/exhaustive-deps

  const setField = (block: Block, field: keyof Edit, value: string) => {
    setEdits((current) => {
      const next = { ...current, [block.ordinal]: { ...current[block.ordinal], [field]: value } }
      const edit = next[block.ordinal]
      if (edit[field] === block[field]) delete edit[field]
      if (Object.keys(edit).length === 0) delete next[block.ordinal]
      return next
    })
  }

  const save = async () => {
    if (!rev) return
    setSaving(true)
    setSaveError(null)
    try {
      const result = await call(api.POST('/api/v1/pages/{page_id}/corrections', {
        params: { path: { page_id: rev.page_id }, header: { 'If-Match': ifMatch(rev.id), 'Idempotency-Key': saveKey } },
        body: { base_revision_id: rev.id, reason: reason.trim(),
                // speaker_layer values come from the SPEAKERS select, i.e. the API's own enum
                changes: Object.entries(edits).map(([ordinal, edit]) =>
                  ({ ordinal: Number(ordinal), ...edit }) as Schemas['BlockChange']) },
      }))
      setPreview(false)
      const query = new URLSearchParams({ saved: result.data.job_id })
      if (itemId) query.set('item', itemId)
      router.replace(`/pages/${result.data.revision.id}?${query}`)
    } catch (caught) {
      setPreview(false)
      if (caught instanceof ApiError && caught.code === 'REVISION_MISMATCH' && caught.etag) {
        // Someone saved this page meanwhile: load their revision and replay my edits on it.
        const latestId = caught.etag.replaceAll('"', '')
        try {
          const latest = (await call(api.GET('/api/v1/page-revisions/{revision_id}', {
            params: { path: { revision_id: latestId } } }))).data
          const rebased = rebase(rev.blocks, latest.blocks, edits)
          setRev(latest)
          setEdits(rebased.edits)
          setConflicts(rebased.conflicts)
          setSaveKey(idempotencyKey())
          setConflictNotice(`Trang vừa được lưu bản sửa khác (bản ${latest.revision_no}). Thay đổi của bạn đã được áp lên bản đó` +
            (rebased.conflicts.length ? `; ${rebased.conflicts.length} khối bị sửa khác nhau, kiểm tra trước khi lưu.` : '.'))
        } catch (reload) {
          setSaveError(reload)
        }
      } else {
        setSaveError(caught)
      }
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return <><PageHeader title="Trang sách" back={{ href: '/books', label: 'Thư viện sách' }} />
      <ErrorState error={loadError} retry={() => setAttempt((n) => n + 1)} /></>
  }
  if (!rev) return <Loading rows={8} />
  const title = book.data?.data.title ?? 'Sách'
  const withBox = rev.blocks.filter((b) => Array.isArray(b.bbox) && b.bbox.length === 4)

  return (
    <>
      <title>{`Trang ${rev.physical_page_number} · ${title} · Kho Bát Tự`}</title>
      <PageHeader
        title={<>Trang {rev.physical_page_number}{rev.printed_page_label ? ` (in: ${rev.printed_page_label})` : ''} <StateBadge labels={PAGE_STATES} value={rev.state} /></>}
        back={{ href: `/versions/${rev.book_version_id}`, label: `${title}${version.data ? ` · ${version.data.data.edition_label}` : ''}` }}
        description={<>Bản {rev.revision_no}{rev.is_latest ? ' (mới nhất)' : ''} · tạo {formatDateTime(rev.created_at)}</>} />
      {!rev.is_latest && (
        <Notice tone="warning">Đây là bản cũ. <Link href={`/pages/${rev.latest_revision_id}${itemId ? `?item=${itemId}` : ''}`}>Mở bản mới nhất</Link> để sửa hoặc duyệt.</Notice>
      )}
      {savedNotice && changed === 0 && !conflictNotice && (
        <Notice tone="ok">Đã lưu bản {rev.revision_no}. Trang được dựng lại trong <Link href={`/jobs/${savedNotice}`}>job {shortId(savedNotice)}</Link>.</Notice>
      )}
      {conflictNotice && <Notice tone="warning">{conflictNotice}</Notice>}
      {itemId && reviewer && (
        <ResolvePanel itemId={itemId} rev={rev} dirty={changed > 0} onResolved={() => setAttempt((n) => n + 1)} />
      )}
      <div className="workspace">
        <section className="panel page-view" aria-label="Ảnh trang">
          <div className="panel-head">
            <h2>Ảnh trang</h2>
            <div className="segmented" role="group" aria-label="Thu phóng">
              {ZOOM.map((z) => (
                <button key={z} type="button" className={`button button-small ${z === scale ? '' : 'button-secondary'}`}
                        aria-pressed={z === scale} onClick={() => setScale(z)}>{z}×</button>
              ))}
            </div>
          </div>
          {imageError ? (
            <p className="muted">Trang không có ảnh (ví dụ DOCX không dựng được bản PDF).</p>
          ) : (
            // 1.5× fills the panel; 2× overflows it and the panel scrolls (never the page).
            <div className="page-image" style={{ width: `${(scale / 1.5) * 100}%` }}>
              {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image, not static media */}
              <img src={`/api/v1/page-revisions/${rev.id}/render?scale=${scale}`} alt={`Ảnh trang ${rev.physical_page_number}`}
                   onError={() => setImageError(true)} />
              {withBox.map((b) => {
                const [x0, y0, x1, y1] = b.bbox
                return (
                  <button key={b.ordinal} type="button" aria-label={`Khối ${b.ordinal}`}
                          className={`bbox${selected === b.ordinal ? ' bbox-selected' : ''}${edits[b.ordinal] ? ' bbox-edited' : ''}`}
                          style={{ left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }}
                          onClick={() => select(b.ordinal)} />
                )
              })}
            </div>
          )}
          <Facts items={quality(rev)} />
        </section>
        <section className="panel page-text" aria-labelledby="blocks-heading">
          <h2 id="blocks-heading">Khối văn bản ({rev.blocks.length})</h2>
          {rev.blocks.length === 0 && <p className="muted">Trang không có chữ (ảnh quét chưa OCR hoặc trang trắng).</p>}
          <ol className="blocks">
            {rev.blocks.map((b) => {
              const edit = edits[b.ordinal]
              const text = edit?.text ?? b.text
              const role = (b.attributes as Record<string, unknown>).role as string | undefined
              const origin = (b.attributes as Record<string, unknown>).origin as string | undefined
              const isTable = b.kind === 'table' && !!b.table_cells
              return (
                <li key={b.ordinal} ref={(el) => { if (el) cards.current.set(b.ordinal, el); else cards.current.delete(b.ordinal) }}
                    className={`block${selected === b.ordinal ? ' block-selected' : ''}${conflicts.includes(b.ordinal) ? ' block-conflict' : ''}`}
                    onFocus={() => setSelected(b.ordinal)}>
                  <div className="block-head">
                    <span className="mono">#{b.ordinal}</span>
                    <Badge>{KINDS[b.kind] ?? b.kind}</Badge>
                    {role && <Badge>{ROLES[role] ?? role}</Badge>}
                    {origin === 'ocr' && <Badge tone="info">OCR</Badge>}
                    {edit && <Badge tone="warning">Đã sửa</Badge>}
                    {conflicts.includes(b.ordinal) && <Badge tone="danger">Xung đột</Badge>}
                    {editable ? (
                      <select aria-label={`Lớp người viết khối ${b.ordinal}`} value={edit?.speaker_layer ?? b.speaker_layer}
                              onChange={(e) => setField(b, 'speaker_layer', e.target.value)}>
                        {Object.entries(SPEAKERS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    ) : <span className="muted small">{SPEAKERS[b.speaker_layer] ?? b.speaker_layer}</span>}
                  </div>
                  {isTable ? (
                    <div className="table-wrap">
                      <table className="cells"><tbody>
                        {b.table_cells!.map((row, r) => <tr key={r}>{row.map((cell, c) => <td key={c}>{cell}</td>)}</tr>)}
                      </tbody></table>
                    </div>
                  ) : editable ? (
                    <textarea aria-label={`Nội dung khối ${b.ordinal}`} value={text} lang="vi"
                              rows={Math.min(12, Math.max(2, Math.ceil(text.length / 70) + text.split('\n').length - 1))}
                              aria-invalid={text.trim() === '' || undefined}
                              onChange={(e) => setField(b, 'text', e.target.value)} />
                  ) : <p className="block-text" lang="vi">{highlight(b.text, b.start_offset, quoted)}</p>}
                  {edit && (
                    <div className="block-foot">
                      {edit.text !== undefined && <Diff before={blocks.get(b.ordinal)?.text ?? ''} after={edit.text} />}
                      <button type="button" className="button button-ghost button-small"
                              onClick={() => setEdits((current) => { const next = { ...current }; delete next[b.ordinal]; return next })}>
                        Hoàn tác khối này
                      </button>
                    </div>
                  )}
                </li>
              )
            })}
          </ol>
        </section>
      </div>
      {editable && (
        <div className="savebar" role="region" aria-label="Lưu bản sửa">
          <span>{changed ? `${changed} khối đã sửa` : 'Chưa có thay đổi'}</span>
          <div className="field">
            <label htmlFor="correction-reason" className="visually-hidden">Lý do sửa</label>
            <input id="correction-reason" type="text" placeholder="Lý do sửa (ví dụ: sửa dấu theo ảnh gốc)" value={reason}
                   maxLength={500} onChange={(e) => setReason(e.target.value)} />
          </div>
          <button type="button" className="button button-secondary" disabled={!changed} onClick={() => setPreview(true)}>Xem thay đổi</button>
          <button type="button" className="button" disabled={!changed || reason.trim().length < 3 || saving ||
                  Object.values(edits).some((e) => e.text !== undefined && e.text.trim() === '')}
                  onClick={() => void save()}>{saving ? 'Đang lưu…' : 'Lưu bản sửa'}</button>
        </div>
      )}
      <FormError error={saveError} />
      <Dialog open={preview} onClose={() => setPreview(false)} title={`Thay đổi trên ${changed} khối`}
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setPreview(false)}>Sửa tiếp</button>
                <button type="button" className="button" disabled={reason.trim().length < 3 || saving}
                        onClick={() => void save()}>Lưu bản sửa</button>
              </>}>
        {Object.entries(edits).map(([ordinal, edit]) => {
          const block = blocks.get(Number(ordinal))
          return (
            <div key={ordinal} className="preview-block">
              <h3>Khối #{ordinal}</h3>
              {edit.speaker_layer && <p>Lớp: {SPEAKERS[block?.speaker_layer ?? 'unknown']} → <strong>{SPEAKERS[edit.speaker_layer]}</strong></p>}
              {edit.text !== undefined && <Diff before={block?.text ?? ''} after={edit.text} />}
            </div>
          )
        })}
        {reason.trim().length < 3 && <Notice tone="warning">Nhập lý do sửa (ít nhất 3 ký tự) ở thanh lưu.</Notice>}
      </Dialog>
    </>
  )
}
