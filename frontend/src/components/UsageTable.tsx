'use client'
// Model usage per profile (docs/12): requests, tokens and cost; never prompt text.
import type { Schemas } from '@/api/client'
import { formatNumber } from '@/lib/format'

export function UsageTable({ rows, caption }: { rows: Schemas['UsageRow'][], caption: string }) {
  if (rows.length === 0) return <p className="muted">Chưa dùng mô hình trong khoảng này.</p>
  return (
    <div className="table-wrap">
      <table>
        <caption className="visually-hidden">{caption}</caption>
        <thead><tr><th scope="col">Profile</th><th scope="col">Lượt gọi</th><th scope="col">Token vào</th>
          <th scope="col">Token ra</th><th scope="col">Chi phí</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.profile_id}:${r.currency}`}>
              <td><code>{r.profile_id.slice(0, 8)}</code></td>
              <td>{formatNumber(r.requests)}</td>
              <td>{formatNumber(r.input_tokens)}</td>
              <td>{formatNumber(r.output_tokens)}</td>
              <td>{r.cost.toFixed(4)} {r.currency}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
