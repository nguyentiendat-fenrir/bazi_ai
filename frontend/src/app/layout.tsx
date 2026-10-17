import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { SessionProvider } from '@/lib/session'
import './globals.css'

export const metadata: Metadata = {
  title: 'Kho Bát Tự',
  description: 'Quản trị kho tri thức Bát Tự: sách, jobs, duyệt nguồn và tra cứu.',
  robots: { index: false, follow: false },
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  )
}
