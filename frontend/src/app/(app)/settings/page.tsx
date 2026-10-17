'use client'
// Personal settings and own model usage (docs/11 /settings). Every change carries If-Match
// with the key's revision ("0" creates it); secrets never appear here.
import { useState } from 'react'

import { api, call, ifMatch, type Schemas } from '@/api/client'
import { ErasureDialog } from '@/components/ErasureDialog'
import { SettingsTabs } from '@/components/SettingsTabs'
import { UsageTable } from '@/components/UsageTable'
import { ErrorState, FormError, Loading, Notice, PageHeader } from '@/components/ui'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Setting = Schemas['SettingDTO']

const PERSONAL: { key: string, label: string, options: [string, string][], fallback: string }[] = [
  { key: 'chat.default_mode', label: 'Chế độ hỏi đáp mặc định', fallback: 'research',
    options: [['research', 'Tra cứu'], ['chart_analysis', 'Luận lá số'], ['comparison', 'So sánh trường phái']] },
  { key: 'ui.theme', label: 'Giao diện', fallback: 'system', options: [['system', 'Theo hệ thống'], ['light', 'Sáng'], ['dark', 'Tối']] },
  { key: 'ui.locale', label: 'Ngôn ngữ', fallback: 'vi', options: [['vi', 'Tiếng Việt'], ['en', 'English']] },
]

export default function SettingsPage() {
  const view = useQuery('settings', () => call(api.GET('/api/v1/settings')))
  const usage = useQuery('usage:own', () => call(api.GET('/api/v1/usage')))
  const [error, setError] = useState<unknown>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const { user, recheck } = useSession()
  const [erasing, setErasing] = useState(false)
  const [erased, setErased] = useState<string | null>(null)

  const save = async (key: string, value: string, current: Setting | undefined) => {
    setError(null)
    setSaved(null)
    try {
      await call(api.PATCH('/api/v1/settings', { params: { header: { 'If-Match': ifMatch(current?.revision ?? 0) } },
        body: { scope: 'user', key, value } }))
      setSaved(key)
      view.reload()
    } catch (caught) {
      setError(caught)
      view.reload()
    }
  }

  return (
    <>
      <title>Cài đặt · Kho Bát Tự</title>
      <PageHeader title="Cài đặt" />
      <SettingsTabs />
      <div className="grid">
        <section className="panel">
          <h2>Tùy chọn của bạn</h2>
          {view.error ? <ErrorState error={view.error} retry={view.reload} /> : !view.data ? <Loading rows={3} /> : (
            <>
              {PERSONAL.map((p) => {
                const current = view.data!.data.settings.find((s) => s.scope === 'user' && s.key === p.key)
                return (
                  <div key={p.key} className="field">
                    <label htmlFor={`set-${p.key}`}>{p.label}</label>
                    <select id={`set-${p.key}`} value={String(current?.value ?? p.fallback)}
                            onChange={(e) => void save(p.key, e.target.value, current)}>
                      {p.options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                    </select>
                    {saved === p.key && <p className="hint" role="status">Đã lưu.</p>}
                  </div>
                )
              })}
              <FormError error={error} />
            </>
          )}
        </section>
        <section className="panel">
          <h2>Mức dùng mô hình của bạn</h2>
          {usage.error ? <ErrorState error={usage.error} retry={usage.reload} /> : !usage.data ? <Loading rows={2} /> : (
            <>
              <p className="muted small">Từ {usage.data.data.from} đến {usage.data.data.to}.</p>
              <UsageTable rows={usage.data.data.own} caption="Mức dùng của bạn" />
            </>
          )}
          {view.data && !view.data.data.runtime.llm_configured && (
            <Notice tone="info">Chưa cấu hình mô hình ngôn ngữ: hỏi đáp trả lời bằng nguồn trích, không có diễn giải của AI.</Notice>
          )}
        </section>
      </div>
      <section className="panel">
        <h2>Dữ liệu của bạn</h2>
        <p className="muted">Lá số, hồ sơ ngày sinh, hội thoại, ca mẫu riêng và cài đặt chỉ bạn xem được. Bạn có thể xóa vĩnh viễn toàn bộ, kèm hoặc không kèm tài khoản.</p>
        {erased && <Notice tone="ok">{erased}</Notice>}
        <button type="button" className="button button-danger" onClick={() => setErasing(true)}>Xóa dữ liệu của tôi…</button>
      </section>
      {user && (
        <ErasureDialog open={erasing} onClose={() => setErasing(false)} email={user.email} onDone={(outcome) => {
          if (outcome.account_deleted) {
            recheck()
            return
          }
          const c = outcome.counts
          setErased(`Đã xóa ${c.charts ?? 0} lá số, ${c.birth_profiles ?? 0} hồ sơ, ${c.conversations ?? 0} hội thoại, ${c.cases ?? 0} ca mẫu.`)
          view.reload()
        }} />
      )}
    </>
  )
}
