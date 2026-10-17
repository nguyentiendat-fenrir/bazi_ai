import type { NextConfig } from 'next'

// In development and E2E, Next proxies /api to FastAPI so the browser sees one origin
// (cookies, CSRF and Origin checks behave as behind the Caddy gateway of docs/03).
const apiOrigin = process.env.BAZI_API_ORIGIN ?? 'http://127.0.0.1:8000'
const dev = process.env.NODE_ENV !== 'production'

// Book text is rendered as plain React text; the policy also blocks any script, frame or
// connection to another origin should something slip through (docs/11 source viewer).
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ''}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ')

const config: NextConfig = {
  // The container image runs the minimal standalone server (infra/frontend.Dockerfile).
  output: process.env.NEXT_OUTPUT === 'standalone' ? 'standalone' : undefined,
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${apiOrigin}/api/:path*` }]
  },
  async headers() {
    return [{
      source: '/:path*',
      headers: [
        { key: 'Content-Security-Policy', value: csp },
        { key: 'X-Content-Type-Options', value: 'nosniff' },
        { key: 'Referrer-Policy', value: 'same-origin' },
        { key: 'X-Frame-Options', value: 'DENY' },
      ],
    }]
  },
}

export default config
