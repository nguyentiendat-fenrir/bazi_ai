// Generate src/api/schema.d.ts from contracts/openapi.json, or (--check) fail when the
// committed file is stale. The backend owns the contract; never edit the output by hand.
import { readFile, writeFile } from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'

const contract = new URL('../../contracts/openapi.json', import.meta.url)
const target = new URL('../src/api/schema.d.ts', import.meta.url)
const banner = '// Generated from contracts/openapi.json by `npm run api:gen`. Do not edit.\n'

const document = JSON.parse(await readFile(contract, 'utf8'))
const generated = banner + astToString(await openapiTS(document))

if (process.argv.includes('--check')) {
  // Windows checkouts may carry CRLF; only the content matters.
  const current = (await readFile(target, 'utf8').catch(() => '')).replaceAll('\r\n', '\n')
  if (current !== generated) {
    console.error('src/api/schema.d.ts is stale: run `npm run api:gen` and commit the result.')
    process.exit(1)
  }
  console.log('API types match contracts/openapi.json')
} else {
  await writeFile(target, generated)
  console.log('Wrote src/api/schema.d.ts')
}
