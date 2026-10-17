'use client'
// Ingestion jobs (docs/11 /jobs): newest first, live while any job is still moving.
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useCallback, useState } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { JobRow } from '@/components/JobRow'
import { Empty, ErrorState, Forbidden, Loading, PageHeader } from '@/components/ui'
import { ACTIVE_JOB_STATES, JOB_STATES } from '@/lib/format'
import { usePagedList } from '@/lib/query'
import { useSession } from '@/lib/session'

type Job = Schemas['JobDTO']
type JobState = Job['state']

function JobsTable() {
  const version = useSearchParams().get('version')
  const [state, setState] = useState<JobState | ''>('')
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/jobs', {
    params: { query: { state: state || undefined, book_version_id: version, limit: 50, cursor } },
  })), [state, version])
  const jobs = usePagedList(`jobs:${state}:${version}`, load, { pollMs: 3000 })
  const moving = jobs.items.some((j) => (ACTIVE_JOB_STATES as readonly string[]).includes(j.state))

  return (
    <>
      <div className="toolbar">
        <div className="field">
          <label htmlFor="job-state">Trạng thái</label>
          <select id="job-state" value={state} onChange={(e) => setState(e.target.value as JobState | '')}>
            <option value="">Tất cả</option>
            {Object.entries(JOB_STATES).map(([value, [text]]) => <option key={value} value={value}>{text}</option>)}
          </select>
        </div>
        {version && <p className="muted">Đang lọc theo một phiên bản. <Link href="/jobs">Bỏ lọc</Link></p>}
        <p className="muted small" aria-live="polite">{moving ? 'Đang cập nhật mỗi 3 giây.' : ''}</p>
      </div>
      {jobs.error && jobs.items.length === 0 ? <ErrorState error={jobs.error} retry={jobs.reload} />
        : jobs.loading ? <Loading rows={5} />
        : jobs.items.length === 0 ? (
          <Empty title="Chưa có job nào" action={<Link className="button" href="/books/upload">Tải sách lên</Link>}>
            Job được tạo khi tải sách với một pipeline profile, sửa trang hoặc xử lý lại phiên bản.
          </Empty>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Danh sách jobs</caption>
                <thead>
                  <tr>
                    <th scope="col">Tạo lúc</th>
                    <th scope="col">Sách</th>
                    <th scope="col">Trạng thái</th>
                    <th scope="col">Bước</th>
                    <th scope="col">Lỗi</th>
                    <th scope="col"><span className="visually-hidden">Mở</span></th>
                  </tr>
                </thead>
                <tbody>{jobs.items.map((job) => <JobRow key={job.id} job={job} />)}</tbody>
              </table>
            </div>
            {jobs.hasMore && (
              <div className="pager">
                <button type="button" className="button button-secondary" onClick={jobs.loadMore}
                        disabled={jobs.loadingMore}>{jobs.loadingMore ? 'Đang tải…' : 'Tải thêm'}</button>
              </div>
            )}
          </>
        )}
    </>
  )
}

export default function JobsPage() {
  const { can } = useSession()
  return (
    <>
      <title>Jobs xử lý · Kho Bát Tự</title>
      <PageHeader title="Jobs xử lý sách" description="Trích xuất, OCR, chia đoạn, vector hóa và niêm phong từng phiên bản sách." />
      {can('library:review')
        ? <Suspense fallback={<Loading rows={5} />}><JobsTable /></Suspense>
        : <Forbidden what="danh sách jobs" />}
    </>
  )
}
