'use client'
// Evidence quoted from a page revision, with a link to read it against the page image.
// Book text renders as plain text only.
import Link from 'next/link'

const SPEAKERS: Record<string, string> = {
  original_author: 'nguyên tác', commentator: 'bình chú', translator: 'người dịch', editor: 'biên tập', unknown: 'chưa rõ lớp',
}

export interface SourceItem {
  evidence_id: string
  page_revision_id: string
  physical_page_number: number
  quote: string
  speaker_layer?: string
}

export function SourceList({ sources, empty = 'Chưa gắn nguồn.' }: { sources: SourceItem[], empty?: string }) {
  if (sources.length === 0) return <p className="muted">{empty}</p>
  return (
    <ul className="citations">
      {sources.map((s) => (
        <li key={s.evidence_id}>
          <span className="muted small">Trang {s.physical_page_number}{s.speaker_layer ? ` · ${SPEAKERS[s.speaker_layer] ?? s.speaker_layer}` : ''}</span>
          <blockquote>{s.quote}</blockquote>
          <Link className="small" href={`/pages/${s.page_revision_id}`}>Mở trang nguồn</Link>
        </li>
      ))}
    </ul>
  )
}
