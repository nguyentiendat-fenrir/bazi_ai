'use client'
// Minimal data loading for client screens: one request per key, optional polling that
// keeps the last data on screen, and results from a stale key are dropped.
import { useCallback, useEffect, useRef, useState } from 'react'

export interface Query<T> {
  data: T | undefined
  error: unknown
  /** Nothing to show yet for this key (first load, no error). */
  loading: boolean
  /** A reload or poll while earlier data stays visible. */
  refreshing: boolean
  reload(): void
  replace(data: T): void
}

export function useQuery<T>(key: string | null, load: () => Promise<T>,
                            options: { pollMs?: number } = {}): Query<T> {
  const [data, setData] = useState<T | undefined>(undefined)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)
  const loader = useRef(load)
  loader.current = load
  const shownKey = useRef<string | null>(null)

  useEffect(() => {
    if (key === null) return
    let live = true
    if (shownKey.current !== key) {
      shownKey.current = key
      setData(undefined)
      setError(null)
    }
    setBusy(true)
    loader.current().then(
      (value) => {
        if (!live) return
        setData(value)
        setError(null)
        setBusy(false)
      },
      (reason) => {
        if (!live) return
        setError(reason)
        setBusy(false)
      })
    return () => { live = false }
  }, [key, tick])

  useEffect(() => {
    if (!options.pollMs || key === null) return
    const timer = setInterval(() => {
      if (typeof document === 'undefined' || !document.hidden) setTick((n) => n + 1)
    }, options.pollMs)
    return () => clearInterval(timer)
  }, [key, options.pollMs])

  const reload = useCallback(() => setTick((n) => n + 1), [])
  const replace = useCallback((value: T) => setData(value), [])
  const fresh = shownKey.current === key
  return {
    data: fresh ? data : undefined,
    error: fresh ? error : null,
    loading: key !== null && (!fresh || (data === undefined && !error)),
    refreshing: fresh && busy && data !== undefined,
    reload, replace,
  }
}

interface PageOf<T> {
  data: T[]
  page?: { has_more: boolean, next_cursor?: string | null }
}

export interface PagedList<T> {
  items: T[]
  error: unknown
  loading: boolean
  hasMore: boolean
  loadingMore: boolean
  loadMore(): void
  reload(): void
}

/** Cursor-paged list: first page per key, "load more" appends the next pages. */
export function usePagedList<T>(key: string | null,
                                load: (cursor: string | null) => Promise<PageOf<T>>,
                                options: { pollMs?: number } = {}): PagedList<T> {
  const first = useQuery(key, () => load(null), options)
  // `loaded` tells "no extra page yet" from "extra pages exhausted" (cursor null in both).
  const [more, setMore] = useState<{ key: string | null, items: T[], cursor: string | null,
                                     loaded: boolean }>(
    { key: null, items: [], cursor: null, loaded: false })
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<unknown>(null)
  const extra = more.key === key ? more : { key, items: [] as T[], cursor: null, loaded: false }
  const cursor = extra.loaded ? extra.cursor
    : first.data?.page?.has_more ? first.data.page.next_cursor ?? null : null

  const loadMore = useCallback(() => {
    if (!cursor) return
    setLoadingMore(true)
    setMoreError(null)
    load(cursor).then(
      (page) => {
        setMore((current) => ({
          key,
          items: [...(current.key === key ? current.items : []), ...page.data],
          cursor: page.page?.has_more ? page.page.next_cursor ?? null : null,
          loaded: true,
        }))
        setLoadingMore(false)
      },
      (reason) => {
        setMoreError(reason)
        setLoadingMore(false)
      })
  }, [cursor, key, load])

  const reload = useCallback(() => {
    setMore({ key: null, items: [], cursor: null, loaded: false })
    first.reload()
  }, [first])

  return {
    items: [...(first.data?.data ?? []), ...extra.items],
    error: first.error ?? moreError,
    loading: first.loading,
    hasMore: !!first.data && !!cursor,
    loadingMore,
    loadMore,
    reload,
  }
}
