'use client'
// First steps for the people who run the library (docs/11 · dashboard): each step is
// read from the real state, links to the screen that does it, and the list hides itself
// once everything is done. Admin-only steps show only to admins.
import Link from 'next/link'

import { api, call } from '@/api/client'
import { Badge } from '@/components/ui'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

interface Step { key: string, done: boolean, title: string, why: string, href: string, action: string }

export function SetupChecklist() {
  const { can } = useSession()
  const admin = can('system:admin')
  const state = useQuery('setup:state', async () => {
    const [books, releases, ontology, rulesets, profiles, settings, metrics] = await Promise.all([
      call(api.GET('/api/v1/books', { params: { query: { limit: 1 } } })),
      call(api.GET('/api/v1/corpus-releases', { params: { query: { limit: 1 } } })),
      call(api.GET('/api/v1/ontology-releases')),
      call(api.GET('/api/v1/rulesets', { params: { query: { state: 'published' } } })),
      call(api.GET('/api/v1/model-profiles')),
      call(api.GET('/api/v1/settings')),
      admin ? call(api.GET('/api/v1/operations/metrics')) : Promise.resolve(null),
    ])
    return { books, releases, ontology, rulesets, profiles, settings, metrics }
  })
  if (!state.data) return null
  const d = state.data
  const llm = d.settings.data.runtime.llm_configured
    || d.profiles.data.some((p) => p.kind === 'llm' && p.active && !p.is_fixture)
  const steps: Step[] = [
    { key: 'books', done: d.books.data.length > 0, title: 'Tải sách lên',
      why: 'Kho tri thức bắt đầu từ sách; mỗi trang được trích, OCR nếu cần và chờ duyệt.',
      href: '/books/upload', action: 'Tải sách' },
    { key: 'publish', done: !!d.releases.data.active, title: 'Publish sách vào kho tra cứu',
      why: 'Chỉ nội dung đã publish mới được tra cứu và trích dẫn trong câu trả lời.',
      href: '/jobs', action: 'Xem jobs' },
    { key: 'ontology', done: d.ontology.data.length > 0, title: 'Duyệt khái niệm và phát hành ontology',
      why: 'Thuật ngữ đã duyệt giúp tìm cả cách gọi khác (Thất Sát / Thiên Quan…) theo đúng trường phái.',
      href: '/knowledge/terms', action: 'Mở tri thức' },
    { key: 'model', done: llm, title: 'Cấu hình mô hình ngôn ngữ',
      why: 'Không có mô hình thì hỏi đáp vẫn trả lời bằng đoạn trích, nhưng không có phần diễn giải.',
      href: admin ? '/settings/models' : '/settings', action: admin ? 'Cấu hình' : 'Xem' },
    { key: 'rules', done: d.rulesets.data.length > 0, title: 'Duyệt quy tắc và kích hoạt bộ quy tắc',
      why: 'Luận lá số theo quy tắc cần quy tắc từ sách được chuyên gia duyệt.',
      href: '/knowledge/rulesets', action: 'Mở bộ quy tắc' },
  ]
  if (admin && d.metrics) {
    const db = d.metrics.data.database as { last_backup_at?: string | null }
    steps.push({ key: 'backup', done: !!db.last_backup_at, title: 'Tạo backup đầu tiên',
      why: 'Chạy scripts/dev backup --dest … trên máy chủ (README · Backup hằng ngày).',
      href: '/settings/system', action: 'Xem vận hành' })
  }
  const remaining = steps.filter((s) => !s.done)
  if (remaining.length === 0) return null
  return (
    <section className="panel setup" aria-labelledby="setup-heading">
      <div className="panel-head">
        <h2 id="setup-heading">Bắt đầu</h2>
        <span className="muted small">{steps.length - remaining.length}/{steps.length} bước đã xong</span>
      </div>
      <ol className="setup-steps">
        {steps.map((s) => (
          <li key={s.key} className={s.done ? 'done' : undefined}>
            <div>
              <strong>{s.title}</strong> {s.done ? <Badge tone="ok">xong</Badge> : <Badge tone="warning">chưa</Badge>}
              {!s.done && <p className="muted small">{s.why}</p>}
            </div>
            {!s.done && <Link className="button button-secondary button-small" href={s.href}>{s.action}</Link>}
          </li>
        ))}
      </ol>
    </section>
  )
}
