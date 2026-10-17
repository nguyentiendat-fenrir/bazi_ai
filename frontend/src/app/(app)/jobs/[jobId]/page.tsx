'use client'
// One job: stage progress, error, durable event log, cancel/retry (docs/11 /jobs).
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

import { api, call, idempotencyKey, type Schemas } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { ErrorState, Facts, Forbidden, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { ACTIVE_JOB_STATES, JOB_STATES, STAGES, formatDateTime, shortId } from '@/lib/format'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type JobEvent = Schemas['JobEvent']

const LEVEL_TONE = { debug: 'neutral', info: 'info', warning: 'warning', error: 'danger' } as const
const EVENT_TEXT: Record<string, string> = {
  JOB_QUEUED: 'Job vào hàng đợi', JOB_STARTED: 'Bắt đầu chạy', STAGE_STARTED: 'Bắt đầu bước',
  STAGE_DONE: 'Xong bước', UNIT_RETRY: 'Thử lại một phần', RETRY_DUE: 'Đến hạn thử lại',
  JOB_FAILED: 'Job thất bại', JOB_CANCELLED: 'Job đã hủy', JOB_SUCCEEDED: 'Job hoàn tất',
}

function summary(event: JobEvent): string {
  const p = event.payload as Record<string, unknown>
  const parts: string[] = []
  if (typeof p.stage === 'string') parts.push(STAGES[p.stage] ?? p.stage)
  if (typeof p.units === 'number') parts.push(`${p.units} phần`)
  if (typeof p.computed === 'number') parts.push(`${p.computed} tính mới, ${p.reused ?? 0} tái dùng`)
  if (typeof p.code === 'string') parts.push(p.code)
  if (typeof p.reason === 'string') parts.push(p.reason)
  if (typeof p.attempt === 'number') parts.push(`lần ${p.attempt}`)
  return parts.join(' · ')
}

/** Durable events, fetched incrementally by sequence number while the job moves. */
function useEvents(jobId: string, live: boolean) {
  const [events, setEvents] = useState<JobEvent[]>([])
  const [error, setError] = useState<unknown>(null)
  const last = useRef(0)
  useEffect(() => {
    let stop = false
    const pull = async () => {
      try {
        for (;;) {
          const page = await call(api.GET('/api/v1/jobs/{job_id}/events', {
            params: { path: { job_id: jobId }, query: { after_seq: last.current, limit: 500 } } }))
          if (stop) return
          if (page.data.length) {
            last.current = page.data[page.data.length - 1].seq
            setEvents((current) => [...current, ...page.data])
          }
          setError(null)
          if (!page.page?.has_more) break
        }
      } catch (caught) {
        if (!stop) setError(caught)
      }
    }
    void pull()
    const timer = live ? setInterval(pull, 2000) : undefined
    return () => { stop = true; if (timer) clearInterval(timer) }
  }, [jobId, live])
  return { events, error }
}

function JobDetail({ jobId }: { jobId: string }) {
  const router = useRouter()
  const job = useQuery(`job:${jobId}`, () =>
    call(api.GET('/api/v1/jobs/{job_id}', { params: { path: { job_id: jobId } } })), { pollMs: 2000 })
  const state = job.data?.data.state
  const live = !state || (ACTIVE_JOB_STATES as readonly string[]).includes(state)
  const { events, error: eventsError } = useEvents(jobId, live)
  const [confirm, setConfirm] = useState<'cancel' | 'retry' | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<unknown>(null)
  const [retryKey] = useState(idempotencyKey)

  if (job.error && !job.data) return <ErrorState error={job.error} retry={job.reload} />
  if (job.loading || !job.data) return <Loading rows={6} />
  const j = job.data.data
  const canCancel = ['queued', 'running', 'retry_wait'].includes(j.state)
  const canRetry = ['failed', 'partial', 'cancelled'].includes(j.state) && j.retried_by.length === 0

  const act = async () => {
    setBusy(true)
    setActionError(null)
    try {
      if (confirm === 'cancel') {
        const done = await call(api.POST('/api/v1/jobs/{job_id}/cancel', { params: { path: { job_id: jobId } } }))
        job.replace(done)
      } else {
        const child = await call(api.POST('/api/v1/jobs/{job_id}/retry', {
          params: { path: { job_id: jobId } }, body: { failed_units_only: true },
          headers: { 'Idempotency-Key': retryKey } }))
        router.push(`/jobs/${child.data.id}`)
      }
      setConfirm(null)
    } catch (caught) {
      setActionError(caught)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <title>{`Job ${shortId(j.id)} · Kho Bát Tự`}</title>
      <PageHeader
        title={<>Job <code>{shortId(j.id)}</code> <StateBadge labels={JOB_STATES} value={j.state} /></>}
        back={{ href: '/jobs', label: 'Jobs xử lý' }}
        description={<><Link href={`/books/${j.book_id}`}>{j.book_title}</Link> · <Link href={`/versions/${j.book_version_id}`}>phiên bản {j.edition_label}</Link></>}
        actions={<>
          {canCancel && <button type="button" className="button button-secondary" onClick={() => setConfirm('cancel')}>Hủy job</button>}
          {canRetry && <button type="button" className="button" onClick={() => setConfirm('retry')}>Thử lại</button>}
        </>} />
      {j.error && (
        <Notice tone={j.state === 'retry_wait' ? 'warning' : 'danger'}>
          <strong><code>{j.error.code}</code></strong> {j.error.message}
          {j.state === 'retry_wait' && j.retry_at && <> · tự thử lại lúc {formatDateTime(j.retry_at)}</>}
          {j.error.retryable ? ' (lỗi tạm thời)' : ' (lỗi vĩnh viễn: thử lại sẽ lặp lại nếu tệp không đổi)'}
        </Notice>
      )}
      {j.retried_by.length > 0 && (
        <Notice>Đã thử lại bằng {j.retried_by.map((id) => <Link key={id} href={`/jobs/${id}`}>job {shortId(id)}</Link>)}.</Notice>
      )}
      <section className="panel" aria-label="Thông tin job">
        <Facts items={[
          ['Tạo lúc', formatDateTime(j.created_at)],
          ['Cập nhật', formatDateTime(j.updated_at)],
          ['Bước hiện tại', j.stage ? STAGES[j.stage] ?? j.stage : '—'],
          ['Generation', <code key="g">{shortId(j.generation_id)}</code>],
          ['Job gốc', j.parent_job_id ? <Link key="p" href={`/jobs/${j.parent_job_id}`}>{shortId(j.parent_job_id)}</Link> : '—'],
          ['Lần thử của phần đang chờ', j.attempt ? String(j.attempt) : '—'],
        ]} />
      </section>
      <section className="panel" aria-labelledby="stages-heading">
        <h2 id="stages-heading">Các bước</h2>
        {j.stages.length === 0 ? <p className="muted">Chưa bắt đầu bước nào.</p> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th scope="col">Bước</th><th scope="col" className="num">Phần việc</th>
                  <th scope="col" className="num">Tính mới</th><th scope="col" className="num">Tái dùng</th>
                  <th scope="col">Xong</th></tr>
              </thead>
              <tbody>
                {j.stages.map((s) => (
                  <tr key={s.stage}>
                    <td>{STAGES[s.stage] ?? s.stage}</td>
                    <td className="num">{s.units}</td>
                    <td className="num">{s.done ? s.computed : '—'}</td>
                    <td className="num">{s.done ? s.reused : '—'}</td>
                    <td>{s.done ? 'Xong' : 'Đang chạy hoặc dừng ở đây'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel" aria-labelledby="events-heading">
        <h2 id="events-heading">Nhật ký ({events.length})</h2>
        {eventsError ? <ErrorState error={eventsError} /> : null}
        <ol className="events" aria-live="polite">
          {events.map((e) => (
            <li key={e.seq}>
              <span className="mono muted">#{e.seq}</span>
              <span className={`badge badge-${LEVEL_TONE[e.level]}`}>{e.level}</span>
              <span className="nowrap muted small">{formatDateTime(e.created_at)}</span>
              <span>{EVENT_TEXT[e.code] ?? e.code}</span>
              <span className="muted">{summary(e)}</span>
            </li>
          ))}
        </ol>
      </section>
      <Dialog open={confirm !== null} onClose={() => setConfirm(null)}
              title={confirm === 'cancel' ? 'Hủy job này?' : 'Thử lại job này?'}
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setConfirm(null)}>Không</button>
                <button type="button" className={`button${confirm === 'cancel' ? ' button-danger' : ''}`}
                        disabled={busy} onClick={() => void act()}>
                  {confirm === 'cancel' ? 'Hủy job' : 'Tạo job thử lại'}
                </button>
              </>}>
        {confirm === 'cancel'
          ? <p>Phần việc đang chạy dừng ở ranh giới an toàn; phần đã xong được giữ để lần sau tái dùng.</p>
          : <p>Job mới chạy lại các phần lỗi của bước <strong>{j.stage ? STAGES[j.stage] ?? j.stage : '—'}</strong>; phần đã thành công được tái dùng.</p>}
        <FormError error={actionError} />
      </Dialog>
    </>
  )
}

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const { can } = useSession()
  if (!can('library:review')) return <Forbidden what="job này" />
  return <JobDetail jobId={jobId} />
}
