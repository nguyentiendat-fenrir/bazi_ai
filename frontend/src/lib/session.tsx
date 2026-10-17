'use client'
// Who is signed in, what they may do, and what happens when the session ends.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, call, setSessionLostListener, type Schemas } from '@/api/client'
import { ApiError } from '@/api/problem'
import { csrf } from './storage'

export type User = Schemas['MeDTO']
export type Capability =
  'library:read' | 'own:data' | 'library:review' | 'library:manage' | 'system:admin'
type Status = 'loading' | 'signed-in' | 'signed-out' | 'unreachable'

interface Session {
  status: Status
  user: User | null
  /** Why the last session ended or could not be checked (shown on the login form). */
  reason: ApiError | null
  can(capability: Capability): boolean
  signIn(email: string, password: string): Promise<User>
  signOut(): Promise<void>
  recheck(): void
}

const SessionContext = createContext<Session | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [reason, setReason] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    call(api.GET('/api/v1/auth/me'), { quietAuth: true }).then(
      (body) => {
        if (!live) return
        setUser(body.data)
        setStatus('signed-in')
      },
      (error: ApiError) => {
        if (!live) return
        setUser(null)
        setStatus(error.status === 401 ? 'signed-out' : 'unreachable')
        if (error.status !== 401) setReason(error)
      })
    return () => { live = false }
  }, [attempt])

  useEffect(() => {
    setSessionLostListener((error) => {
      csrf.clear()
      setUser(null)
      setReason(error)
      setStatus('signed-out')
    })
    return () => setSessionLostListener(null)
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const body = await call(api.POST('/api/v1/auth/login', { body: { email, password } }),
                            { quietAuth: true })
    csrf.set(body.data.csrf_token)
    setUser(body.data.user)
    setReason(null)
    setStatus('signed-in')
    return body.data.user
  }, [])

  const signOut = useCallback(async () => {
    try {
      await call(api.POST('/api/v1/auth/logout'), { quietAuth: true })
    } catch {
      // The cookie may already be gone; the local session ends either way.
    }
    csrf.clear()
    setUser(null)
    setReason(null)
    setStatus('signed-out')
  }, [])

  const value = useMemo<Session>(() => ({
    status, user, reason,
    can: (capability) => !!user?.capabilities.includes(capability),
    signIn, signOut,
    recheck: () => { setStatus('loading'); setAttempt((n) => n + 1) },
  }), [status, user, reason, signIn, signOut])

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('useSession outside SessionProvider')
  return session
}
