'use client'
// Application frame: collapsible sidebar, topbar with API status and the user menu.
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { api, call } from '@/api/client'
import { ROLES } from '@/lib/format'
import { type Capability, useSession } from '@/lib/session'
import { read, write } from '@/lib/storage'

interface NavItem {
  href: string
  label: string
  needs: Capability
  /** Also highlight for these path prefixes. */
  match?: string[]
  /** ...but not for these (a more specific item owns them). */
  except?: string[]
}

// Only screens backed by a real API appear here (docs/11: no placeholder screens).
export const NAV: NavItem[] = [
  { href: '/', label: 'Tổng quan', needs: 'library:read' },
  { href: '/chat', label: 'Hỏi đáp', needs: 'own:data' },
  { href: '/search', label: 'Tra cứu', needs: 'library:read' },
  { href: '/charts', label: 'Lá số', needs: 'own:data' },
  { href: '/books', label: 'Thư viện sách', needs: 'library:read', match: ['/books', '/versions'],
    except: ['/books/upload'] },
  { href: '/books/upload', label: 'Tải sách lên', needs: 'library:review' },
  { href: '/jobs', label: 'Jobs xử lý', needs: 'library:review' },
  { href: '/review', label: 'Duyệt nguồn', needs: 'library:review', match: ['/pages'] },
  { href: '/knowledge/terms', label: 'Tri thức', needs: 'library:review', match: ['/knowledge', '/cases'] },
  { href: '/evaluation', label: 'Đánh giá', needs: 'library:review' },
  { href: '/judge', label: 'Chấm câu trả lời', needs: 'library:review' },
  { href: '/settings', label: 'Cài đặt', needs: 'own:data', match: ['/settings'] },
]

function active(pathname: string, item: NavItem): boolean {
  if (item.href === '/') return pathname === '/'
  const under = (prefix: string) => pathname === prefix || pathname.startsWith(prefix + '/')
  if (item.except?.some(under)) return false
  return [item.href, ...(item.match ?? [])].some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + '/'))
}

type Health = 'checking' | 'ok' | 'degraded' | 'down'

/** API health; for admins also the names of checks that are not ok. */
function useHealth(admin: boolean): [Health, string] {
  const [health, setHealth] = useState<Health>('checking')
  const [detail, setDetail] = useState('')
  useEffect(() => {
    let live = true
    const check = async () => {
      try {
        if (admin) {
          // Ready answers 503 with a body when an essential check fails.
          const { data, response } = await api.GET('/api/v1/health/ready')
          const status = data?.data.status
          if (!live) return
          setHealth(response.ok ? (status === 'ok' ? 'ok' : 'degraded') : 'down')
          setDetail((data?.data.checks ?? []).filter((c) => c.status !== 'ok')
            .map((c) => `${c.name}: ${c.status}`).join(', '))
        } else {
          await call(api.GET('/api/v1/health/live'), { quietAuth: true })
          if (live) setHealth('ok')
        }
      } catch {
        if (live) setHealth('down')
      }
    }
    check()
    const timer = setInterval(check, 30_000)
    return () => { live = false; clearInterval(timer) }
  }, [admin])
  return [health, detail]
}

const HEALTH_TEXT: Record<Health, string> = {
  checking: 'Đang kiểm tra kết nối',
  ok: 'API hoạt động',
  degraded: 'API suy giảm',
  down: 'Mất kết nối API',
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const { user, can, signOut } = useSession()
  const [collapsed, setCollapsed] = useState(false)
  const [health, healthDetail] = useHealth(can('system:admin'))

  useEffect(() => setCollapsed(read('bazi.sidebar') === 'collapsed'), [])
  const toggle = () => {
    setCollapsed((value) => {
      write('bazi.sidebar', value ? 'open' : 'collapsed')
      return !value
    })
  }

  return (
    <div className={`shell${collapsed ? ' shell-collapsed' : ''}`}>
      <a className="skip-link" href="#main">Bỏ qua tới nội dung</a>
      <nav className="sidebar" aria-label="Điều hướng chính">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">八</span>
          <span className="brand-name">Kho Bát Tự</span>
        </div>
        <ul>
          {NAV.filter((item) => can(item.needs)).map((item) => (
            <li key={item.href}>
              <Link href={item.href} aria-current={active(pathname, item) ? 'page' : undefined}
                    title={item.label}>
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="frame">
        <header className="topbar">
          <button type="button" className="button button-ghost" onClick={toggle}
                  aria-expanded={!collapsed} aria-label={collapsed ? 'Mở thanh bên' : 'Thu gọn thanh bên'}>
            ☰
          </button>
          <span className={`health health-${health}`} role="status" aria-live="polite"
                title={healthDetail || undefined}>
            <span className="dot" aria-hidden="true" />{HEALTH_TEXT[health]}
          </span>
          <div className="user">
            <span className="user-email">{user?.email}</span>
            <span className="badge badge-neutral">{ROLES[user?.role ?? ''] ?? user?.role}</span>
            <button type="button" className="button button-ghost" onClick={() => void signOut()}>
              Đăng xuất
            </button>
          </div>
        </header>
        <main id="main" className="main" tabIndex={-1}>{children}</main>
      </div>
    </div>
  )
}
