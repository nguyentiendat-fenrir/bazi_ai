// Word diff for review previews and rebasing local edits onto a newer page revision.

export interface Part {
  kind: 'same' | 'removed' | 'added'
  text: string
}

const MAX_CELLS = 4_000_000

function tokens(text: string): string[] {
  return text.split(/(\s+)/).filter(Boolean)
}

/** Word-level diff (whitespace kept), adjacent parts of one kind merged. */
export function diffWords(before: string, after: string): Part[] {
  const a = tokens(before)
  const b = tokens(after)
  if (a.length * b.length > MAX_CELLS) {
    const whole: Part[] = [{ kind: 'removed', text: before }, { kind: 'added', text: after }]
    return whole.filter((p) => p.text)
  }
  // lcs[i][j] = longest common subsequence of a[i:] and b[j:]
  const width = b.length + 1
  const lcs = new Uint32Array((a.length + 1) * width)
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i * width + j] = a[i] === b[j] ? lcs[(i + 1) * width + j + 1] + 1
        : Math.max(lcs[(i + 1) * width + j], lcs[i * width + j + 1])
    }
  }
  const parts: Part[] = []
  const push = (kind: Part['kind'], text: string) => {
    const last = parts[parts.length - 1]
    if (last && last.kind === kind) last.text += text
    else parts.push({ kind, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push('same', a[i]); i++; j++
    } else if (lcs[(i + 1) * width + j] >= lcs[i * width + j + 1]) {
      push('removed', a[i]); i++
    } else {
      push('added', b[j]); j++
    }
  }
  while (i < a.length) push('removed', a[i++])
  while (j < b.length) push('added', b[j++])
  return parts
}

export interface BlockFields {
  ordinal: number
  text: string
  speaker_layer: string
}

export type Edit = Partial<Pick<BlockFields, 'text' | 'speaker_layer'>>

/**
 * Re-apply edits made on `base` to `latest` (someone saved in between). A field the other
 * reviewer did not touch keeps my value; one they changed to the same value is dropped;
 * one they changed differently keeps my value and marks the block as a conflict to check.
 */
export function rebase(base: BlockFields[], latest: BlockFields[], mine: Record<number, Edit>):
  { edits: Record<number, Edit>, conflicts: number[] } {
  const before = new Map(base.map((b) => [b.ordinal, b]))
  const after = new Map(latest.map((b) => [b.ordinal, b]))
  const edits: Record<number, Edit> = {}
  const conflicts: number[] = []
  for (const [key, edit] of Object.entries(mine)) {
    const ordinal = Number(key)
    const was = before.get(ordinal)
    const now = after.get(ordinal)
    if (!was || !now) {
      conflicts.push(ordinal)
      continue
    }
    const kept: Edit = {}
    let conflict = false
    for (const field of ['text', 'speaker_layer'] as const) {
      const value = edit[field]
      if (value === undefined || now[field] === value) continue
      if (now[field] !== was[field]) conflict = true
      kept[field] = value
    }
    if (Object.keys(kept).length) edits[ordinal] = kept
    if (conflict) conflicts.push(ordinal)
  }
  return { edits, conflicts }
}
