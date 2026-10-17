'use client'
import Link from 'next/link'

import type { Schemas } from '@/api/client'
import { StateBadge } from '@/components/ui'
import { JOB_STATES, STAGES, formatDateTime } from '@/lib/format'

type Job = Schemas['JobDTO']

/** One job in a jobs table (columns: time, book, state, stage, error, link). */
export function JobRow({ job }: { job: Job }) {
  return (
    <tr>
      <td className="nowrap">{formatDateTime(job.created_at)}</td>
      <td>
        <Link href={`/books/${job.book_id}`}>{job.book_title}</Link>
        <div className="muted small">
          <Link href={`/versions/${job.book_version_id}`}>Phiên bản {job.edition_label}</Link>
          {job.parent_job_id && ' · thử lại'}
        </div>
      </td>
      <td><StateBadge labels={JOB_STATES} value={job.state} /></td>
      <td>{job.stage ? STAGES[job.stage] ?? job.stage : '—'}</td>
      <td>{job.error ? <code>{job.error.code}</code> : '—'}</td>
      <td><Link href={`/jobs/${job.id}`}>Chi tiết</Link></td>
    </tr>
  )
}
