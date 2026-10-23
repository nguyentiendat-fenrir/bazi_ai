'use client'
// Section tabs shared by the knowledge admin screens (docs/11 /knowledge/*).
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const TABS = [
  { href: '/knowledge/terms', label: 'Khái niệm & thuật ngữ', match: ['/knowledge/terms', '/knowledge/concepts'] },
  { href: '/knowledge/assertions', label: 'Luận điểm', match: ['/knowledge/assertions'] },
  { href: '/knowledge/rules', label: 'Quy tắc', match: ['/knowledge/rules'] },
  { href: '/knowledge/rulesets', label: 'Bộ quy tắc', match: ['/knowledge/rulesets'] },
  { href: '/cases', label: 'Ca mẫu', match: ['/cases'] },
]

export function KnowledgeTabs() {
  const pathname = usePathname()
  return (
    <nav className="tabs" aria-label="Mục tri thức">
      {TABS.map((tab) => {
        const active = tab.match.some((m) => pathname === m || pathname.startsWith(`${m}/`))
        return <Link key={tab.href} href={tab.href} aria-current={active ? 'page' : undefined}>{tab.label}</Link>
      })}
    </nav>
  )
}
