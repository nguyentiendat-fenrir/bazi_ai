// T042: every API URL the frontend names exists in contracts/openapi.json. Calls through the
// typed client are checked by TypeScript; this also covers URLs built by hand (EventSource,
// the upload XHR, page images), which the compiler cannot see.
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const root = new URL('../../', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const contract = JSON.parse(readFileSync(join(root, '../contracts/openapi.json'), 'utf8')) as { paths: Record<string, unknown> }
const templates = Object.keys(contract.paths).map((p) => new RegExp(`^${p.replace(/\{[^}]+\}/g, '[^/]+')}$`))

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sources(path)
    return /\.tsx?$/.test(name) && name !== 'schema.d.ts' ? [path] : []
  })
}

function urls(): { file: string, url: string }[] {
  const found: { file: string, url: string }[] = []
  for (const file of sources(join(root, 'src'))) {
    const text = readFileSync(file, 'utf8')
    for (const match of text.matchAll(/[`'"](\/api\/v1\/[^`'"?\s]*)/g)) {
      found.push({ file: file.slice(root.length), url: match[1].replace(/\$\{[^}]+\}/g, 'x').replace(/\/$/, '') })
    }
  }
  return found
}

test('every /api/v1 URL in the frontend is a contract path', () => {
  const all = urls()
  assert.ok(all.length > 50, 'the scan found the API calls')
  const unknown = all.filter(({ url }) => !templates.some((t) => t.test(url)))
  assert.deepEqual(unknown, [])
})

test('URLs built by hand are the streaming, upload, page image and score export routes', () => {
  const raw = urls().filter(({ url }) => !url.includes('{') && /\/x(\/|$)/.test(url)).map(({ url }) => url)
  for (const url of raw) {
    assert.match(url, /^\/api\/v1\/(runs\/x\/events|page-revisions\/x\/render|judge\/runs\/x\/scores\.csv)$/)
  }
})
