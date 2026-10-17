'use client'
// Every screen except /login: requires a session, otherwise back to the login form.
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'
import type { ReactNode } from 'react'

import { Shell } from '@/components/Shell'
import { ErrorState, Loading } from '@/components/ui'
import { useSession } from '@/lib/session'

export default function AppLayout({ children }: { children: ReactNode }) {
  const { status, reason, recheck } = useSession()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (status === 'signed-out') {
      const here = pathname + (typeof window === 'undefined' ? '' : window.location.search)
      router.replace(here === '/' ? '/login' : `/login?next=${encodeURIComponent(here)}`)
    }
  }, [status, pathname, router])

  if (status === 'unreachable') {
    return <div className="login"><ErrorState error={reason} retry={recheck} /></div>
  }
  if (status !== 'signed-in') {
    return <div className="login"><Loading label="Đang kiểm tra phiên đăng nhập…" /></div>
  }
  return <Shell>{children}</Shell>
}
