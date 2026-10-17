// Vietnamese labels for chart facts; the API keeps stable ASCII ids (docs/08).

export const POSITIONS = ['year', 'month', 'day', 'hour'] as const
export type Position = typeof POSITIONS[number]

export const POSITION_LABELS: Record<Position, string> = {
  year: 'Năm', month: 'Tháng', day: 'Ngày', hour: 'Giờ',
}

export const ELEMENTS: Record<string, string> = {
  wood: 'Mộc', fire: 'Hỏa', earth: 'Thổ', metal: 'Kim', water: 'Thủy',
}

export const TEN_GODS: Record<string, string> = {
  peer: 'Tỷ Kiên', rob_wealth: 'Kiếp Tài', eating_god: 'Thực Thần', hurting_officer: 'Thương Quan',
  indirect_wealth: 'Thiên Tài', direct_wealth: 'Chính Tài', seven_killings: 'Thất Sát',
  direct_officer: 'Chính Quan', indirect_resource: 'Thiên Ấn', direct_resource: 'Chính Ấn',
}

export const GROWTH: Record<string, string> = {
  changsheng: 'Trường sinh', muyu: 'Mộc dục', guandai: 'Quan đới', linguan: 'Lâm quan',
  diwang: 'Đế vượng', shuai: 'Suy', bing: 'Bệnh', si: 'Tử', mu: 'Mộ', jue: 'Tuyệt', tai: 'Thai',
  yang: 'Dưỡng',
}

export const STEMS: Record<string, string> = {
  jia: 'Giáp', yi: 'Ất', bing: 'Bính', ding: 'Đinh', wu: 'Mậu', ji: 'Kỷ', geng: 'Canh',
  xin: 'Tân', ren: 'Nhâm', gui: 'Quý',
}

export const BRANCHES: Record<string, string> = {
  zi: 'Tý', chou: 'Sửu', yin: 'Dần', mao: 'Mão', chen: 'Thìn', si: 'Tỵ', wu: 'Ngọ', wei: 'Mùi',
  shen: 'Thân', you: 'Dậu', xu: 'Tuất', hai: 'Hợi',
}

// Element of each stem/branch id, for the fixed palette (always with a text label).
export const STEM_ELEMENT: Record<string, string> = {
  jia: 'wood', yi: 'wood', bing: 'fire', ding: 'fire', wu: 'earth', ji: 'earth', geng: 'metal',
  xin: 'metal', ren: 'water', gui: 'water',
}
export const BRANCH_ELEMENT: Record<string, string> = {
  zi: 'water', chou: 'earth', yin: 'wood', mao: 'wood', chen: 'earth', si: 'fire', wu: 'fire',
  wei: 'earth', shen: 'metal', you: 'metal', xu: 'earth', hai: 'water',
}

export const RELATIONS: Record<string, string> = {
  stem_combination: 'Thiên can ngũ hợp', stem_clash: 'Thiên can tương xung',
  six_combination: 'Lục hợp', three_combination: 'Tam hợp', half_combination: 'Bán hợp',
  directional_combination: 'Tam hội', clash: 'Lục xung', punishment: 'Hình',
  self_punishment: 'Tự hình', harm: 'Lục hại', destruction: 'Phá',
}

export const WARNINGS: Record<string, string> = {
  boundary_uncertainty: 'Khoảng giờ sinh vượt qua ranh giới trụ: các trụ đó để trống, xem biến thể.',
  approximate_time: 'Không biết giờ sinh: không lập trụ giờ, không giả định 12:00.',
  near_solar_term: 'Giờ sinh rất sát thời điểm tiết khí: trụ tháng (hoặc năm) có thể đổi trong sai số mô hình.',
  historical_offset: 'Múi giờ lịch sử: Asia/Ho_Chi_Minh theo giờ Sài Gòn (UTC+8 một số giai đoạn 1942–1975); người sinh ở miền Bắc thời kỳ đó dùng UTC+7.',
  luck_direction_unknown: 'Chưa chọn giới tính tính vận nên chưa lập đại vận.',
  pending_auxiliary_validation: 'Mệnh cung, thai nguyên theo công thức cũ, chưa được chuyên gia duyệt.',
  day_master_uncertain: 'Trụ ngày chưa chắc chắn: chưa có nhật chủ nên chưa tính thập thần.',
}

export const POLICIES: Record<string, string> = {
  'standard-v1': 'Chuẩn: giờ dân sự, đổi ngày lúc 0:00',
  'zi23-v1': 'Đổi ngày từ giờ Tý (23:00)',
  'solar-time-v1': 'Giờ Mặt Trời thật (cần kinh độ)',
}

export function ganzhi(stem: string, branch: string): string {
  return `${STEMS[stem] ?? stem} ${BRANCHES[branch] ?? branch}`
}

/** "jia-zi" (chart summaries) → "Giáp Tý". */
export function pairLabel(pair: string | null | undefined): string {
  if (!pair) return '—'
  const [stem, branch] = pair.split('-')
  return ganzhi(stem, branch)
}

/** Age in whole years at an ISO instant, from the birth instant (real age, not tuổi mụ). */
export function ageAt(birthUtc: string, instant: string): number {
  const birth = new Date(birthUtc)
  const at = new Date(instant)
  let age = at.getUTCFullYear() - birth.getUTCFullYear()
  if (at.getUTCMonth() < birth.getUTCMonth()
      || (at.getUTCMonth() === birth.getUTCMonth() && at.getUTCDate() < birth.getUTCDate())) age -= 1
  return age
}

export const COMMON_ZONES = [
  ['Asia/Ho_Chi_Minh', 'Việt Nam (Asia/Ho_Chi_Minh)'],
  ['Asia/Bangkok', 'UTC+7 cố định (Asia/Bangkok) — miền Bắc 1959–1975'],
  ['Asia/Shanghai', 'Trung Quốc (Asia/Shanghai)'],
  ['Asia/Hong_Kong', 'Hồng Kông'],
  ['Asia/Taipei', 'Đài Loan'],
  ['Asia/Tokyo', 'Nhật Bản'],
  ['Asia/Seoul', 'Hàn Quốc'],
  ['Asia/Singapore', 'Singapore'],
  ['Australia/Sydney', 'Úc (Sydney)'],
  ['Europe/Paris', 'Pháp / Trung Âu'],
  ['Europe/London', 'Anh'],
  ['America/New_York', 'Mỹ — miền Đông'],
  ['America/Los_Angeles', 'Mỹ — miền Tây'],
  ['UTC', 'UTC'],
] as const

export const TERMS: Record<string, string> = {
  li_chun: 'Lập Xuân', yu_shui: 'Vũ Thủy', jing_zhe: 'Kinh Trập', chun_fen: 'Xuân Phân',
  qing_ming: 'Thanh Minh', gu_yu: 'Cốc Vũ', li_xia: 'Lập Hạ', xiao_man: 'Tiểu Mãn',
  mang_zhong: 'Mang Chủng', xia_zhi: 'Hạ Chí', xiao_shu: 'Tiểu Thử', da_shu: 'Đại Thử',
  li_qiu: 'Lập Thu', chu_shu: 'Xử Thử', bai_lu: 'Bạch Lộ', qiu_fen: 'Thu Phân', han_lu: 'Hàn Lộ',
  shuang_jiang: 'Sương Giáng', li_dong: 'Lập Đông', xiao_xue: 'Tiểu Tuyết', da_xue: 'Đại Tuyết',
  dong_zhi: 'Đông Chí', xiao_han: 'Tiểu Hàn', da_han: 'Đại Hàn',
}

export const CAUSES: Record<string, string> = {
  day_rollover: 'đổi ngày', hour_boundary: 'đổi canh giờ', ...TERMS,
}
