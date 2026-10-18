'use client'
// One chart (docs/11 /charts/[id]): the four pillars with hidden stems and ten gods, luck
// and annual pillars, relations, warnings and variants, and how it was computed.
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useState } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { ChartAnalysis } from '@/components/ChartAnalysis'
import { Dialog } from '@/components/Dialog'
import { ErrorState, Facts, FormError, Loading, Notice, PageHeader } from '@/components/ui'
import {
  BRANCH_ELEMENT, CAUSES, ELEMENTS, GROWTH, POLICIES, POSITION_LABELS, POSITIONS, RELATIONS,
  STEM_ELEMENT, STEMS, TEN_GODS, TERMS, WARNINGS, ageAt, ganzhi,
} from '@/lib/bazi'
import { formatDateTime } from '@/lib/format'
import { useQuery } from '@/lib/query'

type Facts = Schemas['ChartFacts']
type Pillar = Schemas['Pillar']

function Element({ element, children }: { element: string, children: React.ReactNode }) {
  return (
    <span className={`el el-${element}`}>
      {children} <span className="el-label">{ELEMENTS[element] ?? element}</span>
    </span>
  )
}

function PillarTable({ facts }: { facts: Facts }) {
  const pillars = facts.pillars as Record<string, Pillar | null>
  const cell = (position: string, render: (p: Pillar) => React.ReactNode) => {
    const pillar = pillars[position]
    return <td key={position}>{pillar ? render(pillar) : <span className="muted">Chưa biết</span>}</td>
  }
  const rows: [string, (p: Pillar) => React.ReactNode][] = [
    ['Thập thần', (p) => p.ten_god ? TEN_GODS[p.ten_god] ?? p.ten_god : <strong>Nhật chủ</strong>],
    ['Thiên can', (p) => <Element element={STEM_ELEMENT[p.stem]}>{p.stem_label}</Element>],
    ['Địa chi', (p) => <Element element={BRANCH_ELEMENT[p.branch]}>{p.branch_label}</Element>],
    ['Tàng can', (p) => (
      <ul className="hidden-stems">
        {p.hidden_stems.map((h) => (
          <li key={h.stem}><Element element={STEM_ELEMENT[h.stem]}>{STEMS[h.stem] ?? h.stem}</Element>
            <span className="muted small"> · {TEN_GODS[h.ten_god] ?? h.ten_god}</span></li>
        ))}
      </ul>
    )],
    ['Trường sinh', (p) => p.growth_stage ? GROWTH[p.growth_stage] ?? p.growth_stage : '—'],
    ['Nạp âm', (p) => p.na_yin_label ?? '—'],
    ['Không vong', (p) => p.void ? 'Có' : '—'],
  ]
  return (
    <div className="table-wrap">
      <table className="pillars">
        <caption className="visually-hidden">Tứ trụ</caption>
        <thead>
          <tr><th scope="col"><span className="visually-hidden">Hạng mục</span></th>
            {POSITIONS.map((p) => <th key={p} scope="col">Trụ {POSITION_LABELS[p].toLowerCase()}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map(([title, render]) => (
            <tr key={title}><th scope="row">{title}</th>{POSITIONS.map((p) => cell(p, render))}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function localDate(iso: string): string {
  return new Date(iso).toLocaleDateString('vi-VN')
}

function Luck({ facts }: { facts: Facts }) {
  const cycles = facts.cycles
  if (!cycles) return <p className="muted">Chưa lập vận vì trụ tháng chưa chắc chắn.</p>
  const birth = facts.normalized_time.birth_instant_utc
  const now = new Date().toISOString()
  const start = cycles.start_age_components
  const thisYear = cycles.liu_nian.findIndex((y) => y.start_instant <= now && now < y.end_instant)
  const years = cycles.liu_nian.slice(Math.max(0, thisYear - 1), Math.max(0, thisYear - 1) + 12)
  return (
    <>
      <Facts items={[
        ['Chiều vận', cycles.direction === 'forward' ? 'Thuận' : cycles.direction === 'backward' ? 'Nghịch' : 'Chưa xác định'],
        ['Khởi vận', start ? `${start.years} năm ${start.months} tháng ${start.days} ngày${start.hours ? ` ${start.hours} giờ` : ''} sau sinh`
          : cycles.start_range_utc ? `trong khoảng ${cycles.start_range_utc.map(localDate).join(' – ')}` : '—'],
        ['Mốc khởi vận', cycles.start_instant ? formatDateTime(cycles.start_instant) : '—'],
      ]} />
      {cycles.da_yun && (
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Đại vận</caption>
            <thead><tr><th scope="col">#</th><th scope="col">Đại vận</th><th scope="col">Tuổi</th><th scope="col">Từ – đến</th></tr></thead>
            <tbody>
              {cycles.da_yun.map((d) => {
                const current = d.start && d.end && d.start <= now && now < d.end
                return (
                  <tr key={d.index} className={current ? 'current' : undefined} aria-current={current ? 'true' : undefined}>
                    <td>{d.index}</td>
                    <td><Element element={STEM_ELEMENT[d.stem]}>{ganzhi(d.stem, d.branch)}</Element>{current && <span className="badge badge-info"> hiện tại</span>}</td>
                    <td>{d.start ? `${ageAt(birth, d.start)}–${ageAt(birth, d.end!)}` : '—'}</td>
                    <td>{d.start ? `${localDate(d.start)} – ${localDate(d.end!)}` : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <h3>Lưu niên</h3>
      <ul className="years">
        {years.map((y) => {
          const current = y.start_instant <= now && now < y.end_instant
          return (
            <li key={y.solar_term_year} className={current ? 'current' : undefined}>
              <span className="mono">{y.solar_term_year}</span> {ganzhi(y.stem, y.branch)}
              {current && <span className="badge badge-info">năm nay</span>}
            </li>
          )
        })}
      </ul>
      <p className="muted small">Năm tính từ Lập Xuân đến Lập Xuân, không theo Tết âm lịch.</p>
    </>
  )
}

export default function ChartPage() {
  const { chartId } = useParams<{ chartId: string }>()
  const router = useRouter()
  const chart = useQuery(`chart:${chartId}`, () =>
    call(api.GET('/api/v1/charts/{chart_id}', { params: { path: { chart_id: chartId } } })))
  const [confirm, setConfirm] = useState(false)
  const [error, setError] = useState<unknown>(null)

  if (chart.error) {
    return <><PageHeader title="Lá số" back={{ href: '/charts', label: 'Lá số' }} />
      <ErrorState error={chart.error} retry={chart.reload} /></>
  }
  if (chart.loading || !chart.data) return <Loading rows={8} />
  const c = chart.data.data
  const facts = c.facts
  const input = facts.input_snapshot
  const time = facts.normalized_time
  const title = c.profile_label ?? 'Lá số'

  const remove = async () => {
    try {
      await call(api.DELETE('/api/v1/charts/{chart_id}', { params: { path: { chart_id: chartId } } }))
      router.replace('/charts')
    } catch (caught) {
      setError(caught)
    }
  }

  return (
    <>
      <title>{`${title} · Kho Bát Tự`}</title>
      <PageHeader title={title} back={{ href: '/charts', label: 'Lá số' }}
                  description={`${POLICIES[c.policy_id] ?? c.policy_id} · lập ${formatDateTime(c.created_at)}`}
                  actions={<>
                    <Link className="button" href={`/chat?chart=${c.id}`}>Hỏi về lá số này</Link>
                    <button type="button" className="button button-ghost" onClick={() => setConfirm(true)}>Xóa…</button>
                  </>} />
      {facts.warnings.map((w) => (
        <Notice key={w.code} tone={w.code === 'pending_auxiliary_validation' ? 'info' : 'warning'}>
          {WARNINGS[w.code] ?? w.detail}
        </Notice>
      ))}
      <section className="panel" aria-labelledby="pillars-heading">
        <h2 id="pillars-heading">Tứ trụ</h2>
        <PillarTable facts={facts} />
      </section>
      {facts.variants.length > 0 && (
        <section className="panel" aria-labelledby="variants-heading">
          <h2 id="variants-heading">Các khả năng theo khoảng giờ sinh</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th scope="col">Từ (UTC)</th><th scope="col">Đến (UTC)</th><th scope="col">Trụ</th><th scope="col">Lý do đổi</th></tr></thead>
              <tbody>
                {facts.variants.map((v) => (
                  <tr key={v.from_utc}>
                    <td className="nowrap">{formatDateTime(v.from_utc)}</td>
                    <td className="nowrap">{formatDateTime(v.to_utc)}</td>
                    <td>{Object.entries(v.pillars).map(([p, g]) => `${POSITION_LABELS[p as keyof typeof POSITION_LABELS]}: ${ganzhi(g.stem, g.branch)}`).join(' · ')}</td>
                    <td>{v.reasons.map((r) => `${POSITION_LABELS[r.position as keyof typeof POSITION_LABELS] ?? r.position} (${CAUSES[r.cause] ?? r.cause})`).join(', ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <div className="grid">
        <section className="panel" aria-labelledby="birth-heading">
          <h2 id="birth-heading">Thời điểm sinh</h2>
          <Facts items={[
            ['Nhập', input.calendar_system === 'gregorian' ? `${input.local_datetime} (dương lịch)`
              : `${input.lunar_date?.day}/${input.lunar_date?.month}${input.lunar_date?.is_leap_month ? ' nhuận' : ''}/${input.lunar_date?.year} ${input.local_time} (${input.calendar_system === 'lunar_vn' ? 'âm lịch VN' : 'âm lịch TQ'})`],
            ['Múi giờ', `${input.timezone} (UTC${time.utc_offset_seconds >= 0 ? '+' : '−'}${Math.abs(time.utc_offset_seconds) / 3600})`],
            ['Giờ dân sự', time.civil_local.replace('T', ' ')],
            ['Đồng hồ tính trụ', time.pillar_clock_local.replace('T', ' ')],
            ['Thời điểm UTC', time.birth_instant_utc],
            ['Độ chính xác', input.time_accuracy === 'minute' ? `đến phút${input.uncertainty_minutes ? ` ±${input.uncertainty_minutes}′` : ''}` : input.time_accuracy === 'hour' ? 'khoảng giờ' : 'không biết giờ'],
            ['Tiết trước', `${TERMS[time.previous_jie.key] ?? time.previous_jie.key} · ${formatDateTime(time.previous_jie.instant_utc)}`],
            ['Tiết sau', `${TERMS[time.next_jie.key] ?? time.next_jie.key} · ${formatDateTime(time.next_jie.instant_utc)}`],
            ...(time.eot_minutes !== null ? [['Phương trình thời gian', `${time.eot_minutes} phút`] as [string, string],
              ['Hiệu chỉnh kinh độ', `${time.longitude_correction_minutes} phút`] as [string, string]] : []),
          ]} />
        </section>
        <section className="panel" aria-labelledby="relations-heading">
          <h2 id="relations-heading">Quan hệ can chi</h2>
          {facts.relations.length === 0 ? <p className="muted">Không có quan hệ đáng kể.</p> : (
            <ul className="plain-list">
              {facts.relations.map((r, i) => (
                <li key={i}>
                  <strong>{RELATIONS[r.type] ?? r.type}</strong>{r.element && ` (${ELEMENTS[r.element]})`}:{' '}
                  {r.positions.map((p) => POSITION_LABELS[p as keyof typeof POSITION_LABELS] ?? p).join(' – ')}
                  <span className="muted small"> · {r.completeness === 'full' ? 'đủ' : 'thiếu thành phần'}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">Quan hệ là cấu hình tính được, chưa phải đã “hóa” hay sự kiện đời sống.</p>
        </section>
      </div>
      <section className="panel" aria-labelledby="analysis-heading">
        <h2 id="analysis-heading">Luận theo quy tắc</h2>
        <ChartAnalysis chartId={c.id} />
      </section>
      <section className="panel" aria-labelledby="luck-heading">
        <h2 id="luck-heading">Đại vận và lưu niên</h2>
        <Luck facts={facts} />
      </section>
      <details className="panel">
        <summary>Cách tính (policy, engine, hash)</summary>
        <pre className="mono small trace">{JSON.stringify({ policy: facts.policy_snapshot, engine: facts.engine_manifest,
          auxiliary: facts.auxiliary, facts_hash: facts.facts_hash }, null, 2)}</pre>
      </details>
      <Dialog open={confirm} onClose={() => setConfirm(false)} title="Xóa lá số này?"
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setConfirm(false)}>Không</button>
                <button type="button" className="button button-danger" onClick={() => void remove()}>Xóa lá số</button>
              </>}>
        <p>Lá số “{title}” và dữ liệu sinh mã hóa của nó bị xóa. Hồ sơ (nếu có) vẫn giữ.</p>
        <FormError error={error} />
      </Dialog>
    </>
  )
}
