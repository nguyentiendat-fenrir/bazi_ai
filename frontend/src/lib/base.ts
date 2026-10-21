// Public base path of the app (e.g. "/bazi" when it is published under a sub-path such as a
// Tailscale Funnel mount). Fixed at build time (NEXT_PUBLIC_BASE_PATH); empty serves from "/".
// Next's <Link>, router and assets add it themselves; URLs built by hand (API client, SSE,
// uploads, images, downloads, plain <a>) go through withBase.
export const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH ?? '').replace(/\/+$/, '')

export function withBase(path: string): string {
  return BASE_PATH + path
}
