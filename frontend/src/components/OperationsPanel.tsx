'use client'
// Operations metrics and local alerts for admins (docs/12 · Observability): counts only,
// refreshed every 30 s; nothing private is in this response.
import { api, call } from '@/api/client'
import { Badge, ErrorState, Facts, Loading, Notice } from '@/components/ui'
import { formatBytes, formatDateTime, formatNumber } from '@/lib/format'
import { useQuery } from '@/lib/query'

const SEVERITY = { high: 'danger', medium: 'warning', low: 'neutral' } as const

type Counts = Record<string, number>

function counts(value: unknown): string {
  const entries = Object.entries((value ?? {}) as Counts)
  return entries.length ? entries.map(([k, n]) => `${k} ${formatNumber(n)}`).join(' · ') : '—'
}

const REASONS: Record<string, string> = {
  wrong_source: 'trích sai nguồn', missing_source: 'thiếu nguồn', wrong_school: 'lẫn trường phái',
  calculation: 'sai tính toán', too_certain: 'khẳng định quá mức', unclear: 'khó hiểu', other: 'khác',
}

function feedbackLine(totals: Record<string, unknown> | undefined): string {
  if (!totals) return '—'
  const reasons = Object.entries((totals.categories ?? {}) as Counts)
    .sort((a, b) => b[1] - a[1]).map(([k, n]) => `${REASONS[k] ?? k} ${n}`)
  return `${formatNumber(Number(totals.helpful ?? 0))} hữu ích · ${formatNumber(Number(totals.not_helpful ?? 0))} chưa đúng`
    + (reasons.length ? ` (${reasons.join(', ')})` : '')
}

export function OperationsAlerts({ compact }: { compact?: boolean }) {
  const metrics = useQuery('operations:metrics', () => call(api.GET('/api/v1/operations/metrics')), { pollMs: 30_000 })
  if (metrics.error) return <ErrorState error={metrics.error} retry={metrics.reload} />
  if (!metrics.data) return <Loading rows={compact ? 1 : 3} />
  const { alerts, database, process } = metrics.data.data
  const db = database as Record<string, Record<string, unknown>> & { last_backup_at?: string | null }
  const proc = process as { retrieval_ms: { samples: number, p50: number | null, p95: number | null },
    disk: { free_bytes: number, total_bytes: number, free_share: number } | null }
  return (
    <div className="operations">
      {alerts.length === 0
        ? <Notice tone="ok">Không có cảnh báo vận hành.</Notice>
        : (
          <ul className="plain-list" aria-label="Cảnh báo vận hành">
            {alerts.map((a) => (
              <li key={a.code}><Badge tone={SEVERITY[a.severity]}>{a.code}</Badge> {a.message}</li>
            ))}
          </ul>
        )}
      {!compact && (
        <Facts items={[
          ['Job xử lý sách', counts(db.ingestion.by_state)],
          ['Lỗi 24 giờ', `${formatNumber(Number(db.ingestion.failed_24h))} job sách · ${formatNumber(Number(db.chat.failed_24h))} câu trả lời`],
          ['Câu trả lời', `${formatNumber(Number(db.chat.completed_24h))} trong 24 giờ · ${formatNumber(Number(db.chat.rejected_claims_24h))} nhận định bị loại`],
          ['Trang', counts(db.pages)],
          ['Quy tắc 24 giờ', counts(db.rules_24h)],
          ['Tra cứu (tiến trình này)', proc.retrieval_ms.samples
            ? `p50 ${proc.retrieval_ms.p50} ms · p95 ${proc.retrieval_ms.p95} ms (${proc.retrieval_ms.samples} lần)` : 'chưa có'],
          ['Ổ lưu tệp', proc.disk ? `còn ${formatBytes(proc.disk.free_bytes)} / ${formatBytes(proc.disk.total_bytes)}` : 'không đo (lưu trữ ngoài)'],
          ['Đánh giá 7 ngày', feedbackLine(db.feedback_7d as Record<string, unknown> | undefined)],
          ['Backup gần nhất', db.last_backup_at ? formatDateTime(db.last_backup_at) : 'chưa có'],
        ]} />
      )}
    </div>
  )
}
