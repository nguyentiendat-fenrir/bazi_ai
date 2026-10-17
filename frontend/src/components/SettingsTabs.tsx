'use client'
// Section tabs for /settings; each tab shows only to users whose role has the API behind it.
import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { useSession, type Capability } from '@/lib/session'

const TABS: { href: string, label: string, needs: Capability }[] = [
  { href: '/settings', label: 'Cá nhân', needs: 'own:data' },
  { href: '/settings/models', label: 'Mô hình AI', needs: 'system:admin' },
  { href: '/settings/system', label: 'Hệ thống & ngân sách', needs: 'system:admin' },
  { href: '/settings/users', label: 'Người dùng', needs: 'system:admin' },
  { href: '/settings/releases', label: 'Bản kho tra cứu', needs: 'library:review' },
]

export function SettingsTabs() {
  const pathname = usePathname()
  const { can } = useSession()
  return (
    <nav className="tabs" aria-label="Mục cài đặt">
      {TABS.filter((t) => can(t.needs)).map((t) => (
        <Link key={t.href} href={t.href} aria-current={pathname === t.href ? 'page' : undefined}>{t.label}</Link>
      ))}
    </nav>
  )
}
