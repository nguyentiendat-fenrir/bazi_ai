'use client'
// New chart (docs/11 /charts/new): Gregorian or lunar date, time zone, time accuracy,
// policy; errors of the engine (gap, fold, range) are shown on the field they concern.
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { ApiError } from '@/api/problem'
import { ErrorState, FormError, Loading, Notice, PageHeader } from '@/components/ui'
import { COMMON_ZONES, POLICIES } from '@/lib/bazi'
import { useQuery } from '@/lib/query'

type Calendar = 'gregorian' | 'lunar_vn' | 'lunar_cn'
type Accuracy = 'minute' | 'hour' | 'unknown'
type BirthInput = Schemas['BirthInput']

const ENGINE_MESSAGES: Record<string, string> = {
  NONEXISTENT_TIME: 'Giờ này không tồn tại ở múi giờ đã chọn (đồng hồ nhảy tới khi đổi giờ mùa hè).',
  AMBIGUOUS_TIME: 'Giờ này xảy ra hai lần (lùi đồng hồ cuối giờ mùa hè): chọn lần thứ nhất hay thứ hai.',
  UNSUPPORTED_RANGE: 'Chỉ hỗ trợ ngày sinh từ 1900 đến 2100.',
  INVALID_DATETIME: 'Ngày giờ không hợp lệ.',
  INVALID_LUNAR_DATE: 'Ngày âm lịch không tồn tại (tháng thiếu hoặc không có tháng nhuận này).',
  TIMEZONE_UNKNOWN: 'Không nhận ra múi giờ IANA này.',
  LONGITUDE_REQUIRED: 'Giờ Mặt Trời thật cần kinh độ nơi sinh.',
}

// Engine errors shown next to their field instead of in the form-level box.
const INLINE = ['local_datetime', 'lunar_date', 'timezone', 'longitude']

function fieldOf(path: string): string {
  return path.replace(/^body\./, '').replace(/^birth_input\./, '')
}

export default function NewChartPage() {
  const router = useRouter()
  const catalog = useQuery('calculation-policies', () => call(api.GET('/api/v1/calculation-policies')))
  const [calendar, setCalendar] = useState<Calendar>('gregorian')
  const [date, setDate] = useState('')
  const [time, setTime] = useState('')
  const [lunar, setLunar] = useState({ year: '', month: '1', day: '1', leap: false })
  const [accuracy, setAccuracy] = useState<Accuracy>('minute')
  const [uncertainty, setUncertainty] = useState('0')
  const [zoneChoice, setZoneChoice] = useState<string>('Asia/Ho_Chi_Minh')
  const [otherZone, setOtherZone] = useState('')
  const [fold, setFold] = useState<0 | 1 | null>(null)
  const [needsFold, setNeedsFold] = useState(false)
  const [sex, setSex] = useState<'male' | 'female' | 'unspecified'>('unspecified')
  const [policy, setPolicy] = useState('standard-v1')
  const [longitude, setLongitude] = useState('')
  const [saveProfile, setSaveProfile] = useState(false)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  const solar = useMemo(() => catalog.data?.data.policies.find((p) => p.id === policy)?.clock_basis
    === 'apparent_solar', [catalog.data, policy])
  const zone = zoneChoice === 'other' ? otherZone.trim() : zoneChoice

  const fieldError = (name: string): string | undefined => {
    if (!(error instanceof ApiError)) return undefined
    const hit = error.fieldErrors.find((f) => fieldOf(f.path) === name || fieldOf(f.path).startsWith(name + '.'))
    if (!hit) return undefined
    return ENGINE_MESSAGES[error.code] ?? hit.message
  }

  const birthInput = (): BirthInput => {
    const clock = accuracy === 'unknown' ? '00:00' : time
    const base = {
      timezone: zone, time_accuracy: accuracy, sex_for_luck: sex, policy_id: policy,
      uncertainty_minutes: accuracy === 'unknown' ? 0 : Number(uncertainty) || 0,
      ...(fold !== null ? { fold } : {}),
      ...(solar && longitude.trim() ? { longitude: Number(longitude) } : {}),
    }
    if (calendar === 'gregorian') {
      return { ...base, calendar_system: 'gregorian', local_datetime: `${date}T${clock}` } as BirthInput
    }
    return {
      ...base, calendar_system: calendar, local_time: clock,
      lunar_date: { year: Number(lunar.year), month: Number(lunar.month), day: Number(lunar.day),
                    is_leap_month: lunar.leap },
    } as BirthInput
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const birth_input = birthInput()
      let chart
      if (saveProfile) {
        const profile = await call(api.POST('/api/v1/birth-profiles', {
          body: { label: label.trim() || 'Hồ sơ', birth_input } }))
        chart = await call(api.POST('/api/v1/charts', { body: { profile_id: profile.data.id } }))
      } else {
        chart = await call(api.POST('/api/v1/charts', { body: { birth_input } }))
      }
      router.push(`/charts/${chart.data.id}`)
    } catch (caught) {
      setError(caught)
      if (caught instanceof ApiError && caught.code === 'AMBIGUOUS_TIME') setNeedsFold(true)
    } finally {
      setBusy(false)
    }
  }

  if (catalog.error) return <ErrorState error={catalog.error} retry={catalog.reload} />
  if (catalog.loading || !catalog.data) return <Loading rows={6} />
  const range = catalog.data.data.range
  const ready = (calendar === 'gregorian' ? !!date : !!lunar.year) && (accuracy === 'unknown' || !!time)
    && !!zone && (!solar || longitude.trim() !== '') && (!needsFold || fold !== null)

  return (
    <>
      <title>Lập lá số · Kho Bát Tự</title>
      <PageHeader title="Lập lá số" back={{ href: '/charts', label: 'Lá số' }}
                  description={`Ngày sinh ${range.first_year}–${range.last_year}. Giờ sinh theo đồng hồ địa phương; múi giờ quyết định độ lệch.`} />
      <form className="panel chart-form" onSubmit={submit} noValidate>
        <fieldset className="field">
          <legend className="label">Lịch</legend>
          <div className="choices">
            {([['gregorian', 'Dương lịch'], ['lunar_vn', 'Âm lịch Việt Nam'], ['lunar_cn', 'Âm lịch Trung Quốc']] as const)
              .map(([value, text]) => (
                <label key={value} className="checkbox">
                  <input type="radio" name="calendar" checked={calendar === value} onChange={() => setCalendar(value)} />
                  <span>{text}</span>
                </label>
              ))}
          </div>
        </fieldset>
        <div className="form-grid">
          {calendar === 'gregorian' ? (
            <div className="field">
              <label htmlFor="birth-date">Ngày sinh (dương lịch)</label>
              <input id="birth-date" type="date" value={date} min={`${range.first_year}-01-01`}
                     max={`${range.last_year}-12-31`} onChange={(e) => setDate(e.target.value)}
                     aria-invalid={!!fieldError('local_datetime') || undefined} />
              {fieldError('local_datetime') && <span className="error">{fieldError('local_datetime')}</span>}
            </div>
          ) : (
            <div className="field">
              <span className="label">Ngày sinh (âm lịch)</span>
              <div className="inline-fields">
                <input aria-label="Năm âm lịch" type="number" placeholder="Năm" value={lunar.year}
                       onChange={(e) => setLunar({ ...lunar, year: e.target.value })} />
                <select aria-label="Tháng âm lịch" value={lunar.month} onChange={(e) => setLunar({ ...lunar, month: e.target.value })}>
                  {Array.from({ length: 12 }, (_, i) => <option key={i} value={i + 1}>Tháng {i + 1}</option>)}
                </select>
                <select aria-label="Ngày âm lịch" value={lunar.day} onChange={(e) => setLunar({ ...lunar, day: e.target.value })}>
                  {Array.from({ length: 30 }, (_, i) => <option key={i} value={i + 1}>Ngày {i + 1}</option>)}
                </select>
              </div>
              <label className="checkbox"><input type="checkbox" checked={lunar.leap}
                     onChange={(e) => setLunar({ ...lunar, leap: e.target.checked })} /><span>Tháng nhuận</span></label>
              {fieldError('lunar_date') && <span className="error">{fieldError('lunar_date')}</span>}
            </div>
          )}
          <div className="field">
            <label htmlFor="accuracy">Độ chính xác giờ sinh</label>
            <select id="accuracy" value={accuracy} onChange={(e) => setAccuracy(e.target.value as Accuracy)}>
              <option value="minute">Biết đến phút</option>
              <option value="hour">Chỉ biết khoảng giờ</option>
              <option value="unknown">Không biết giờ</option>
            </select>
          </div>
          {accuracy !== 'unknown' && (
            <div className="field">
              <label htmlFor="birth-time">Giờ sinh</label>
              <input id="birth-time" type="time" value={time} onChange={(e) => setTime(e.target.value)} />
            </div>
          )}
          {accuracy !== 'unknown' && (
            <div className="field">
              <label htmlFor="uncertainty">Sai số (± phút)</label>
              <input id="uncertainty" type="number" min={0} max={720} value={uncertainty}
                     onChange={(e) => setUncertainty(e.target.value)} />
            </div>
          )}
        </div>
        {accuracy === 'unknown' && (
          <Notice>Không giả định giờ 12:00: lá số sẽ không có trụ giờ; trụ nào đổi trong ngày sẽ để trống kèm các khả năng.</Notice>
        )}
        <div className="form-grid">
          <div className="field">
            <label htmlFor="zone">Múi giờ nơi sinh</label>
            <select id="zone" value={zoneChoice} onChange={(e) => { setZoneChoice(e.target.value); setFold(null); setNeedsFold(false) }}>
              {COMMON_ZONES.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
              <option value="other">Khác (nhập tên IANA)…</option>
            </select>
            {zoneChoice === 'other' && (
              <input aria-label="Tên múi giờ IANA" type="text" placeholder="ví dụ Europe/Berlin" value={otherZone}
                     onChange={(e) => setOtherZone(e.target.value)} />
            )}
            {fieldError('timezone') && <span className="error">{fieldError('timezone')}</span>}
          </div>
          <div className="field">
            <label htmlFor="policy">Cách tính</label>
            <select id="policy" value={policy} onChange={(e) => setPolicy(e.target.value)}>
              {catalog.data.data.policies.map((p) => (
                <option key={String(p.id)} value={String(p.id)}>{POLICIES[String(p.id)] ?? String(p.id)}</option>
              ))}
            </select>
          </div>
          {solar && (
            <div className="field">
              <label htmlFor="longitude">Kinh độ nơi sinh (độ, Đông dương)</label>
              <input id="longitude" type="number" step="0.01" min={-180} max={180} value={longitude}
                     placeholder="ví dụ 105.85 (Hà Nội)" onChange={(e) => setLongitude(e.target.value)} />
              {fieldError('longitude') && <span className="error">{fieldError('longitude')}</span>}
            </div>
          )}
        </div>
        {needsFold && (
          <fieldset className="field">
            <legend className="label">Giờ này xảy ra hai lần — chọn</legend>
            <label className="checkbox"><input type="radio" name="fold" checked={fold === 0} onChange={() => setFold(0)} /><span>Lần thứ nhất (trước khi lùi đồng hồ)</span></label>
            <label className="checkbox"><input type="radio" name="fold" checked={fold === 1} onChange={() => setFold(1)} /><span>Lần thứ hai (sau khi lùi đồng hồ)</span></label>
          </fieldset>
        )}
        <fieldset className="field">
          <legend className="label">Giới tính tính vận</legend>
          <span className="hint">Chỉ dùng để tính chiều đại vận (thuận/nghịch), không suy từ tên.</span>
          <div className="choices">
            {([['male', 'Nam'], ['female', 'Nữ'], ['unspecified', 'Không xác định']] as const).map(([value, text]) => (
              <label key={value} className="checkbox">
                <input type="radio" name="sex" checked={sex === value} onChange={() => setSex(value)} />
                <span>{text}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="checkbox">
          <input type="checkbox" checked={saveProfile} onChange={(e) => setSaveProfile(e.target.checked)} />
          <span>Lưu thành hồ sơ để lập lại sau (dữ liệu sinh được mã hóa)</span>
        </label>
        {saveProfile && (
          <div className="field">
            <label htmlFor="profile-label">Tên hồ sơ</label>
            <input id="profile-label" type="text" maxLength={200} value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
        )}
        {error instanceof ApiError && error.code === 'AMBIGUOUS_TIME' ? (
          <Notice tone="warning">{ENGINE_MESSAGES.AMBIGUOUS_TIME}</Notice>
        ) : error && !INLINE.some((name) => fieldError(name)) ? <FormError error={error} /> : null}
        <div className="actions">
          <button type="submit" className="button" disabled={busy || !ready}>{busy ? 'Đang lập…' : 'Lập lá số'}</button>
          <Link className="button button-ghost" href="/charts">Hủy</Link>
        </div>
        <p className="muted small">Lá số tính bằng engine riêng (không gọi mô hình AI); kết quả gồm cả cách tính và cảnh báo.</p>
      </form>
    </>
  )
}
