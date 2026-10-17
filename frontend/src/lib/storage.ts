// Browser storage that never throws: private windows, blocked site data and server
// rendering all fall back to memory, so a screen still works without it.

const memory = new Map<string, string>()

function store(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

export function read(key: string): string | null {
  try {
    return store()?.getItem(key) ?? memory.get(key) ?? null
  } catch {
    return memory.get(key) ?? null
  }
}

export function write(key: string, value: string | null): void {
  if (value === null) memory.delete(key)
  else memory.set(key, value)
  try {
    if (value === null) store()?.removeItem(key)
    else store()?.setItem(key, value)
  } catch {
    // memory copy above is enough for this tab
  }
}

// The CSRF token comes only from the login response (the server keeps a hash), so it is
// kept for the session's lifetime and shared by the tabs of this browser.
const CSRF_KEY = 'bazi.csrf'

export const csrf = {
  get: () => read(CSRF_KEY),
  set: (token: string) => write(CSRF_KEY, token),
  clear: () => write(CSRF_KEY, null),
}
