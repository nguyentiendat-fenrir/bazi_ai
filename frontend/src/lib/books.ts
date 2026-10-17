// Book display helpers shared by the library screens.
import type { Schemas } from '@/api/client'

type Book = Schemas['BookDTO']

const AUTHOR_ROLES: Record<string, string> = {
  author: 'tác giả', commentator: 'bình chú', translator: 'dịch', editor: 'biên tập',
}

export function authorLine(book: Book): string {
  if (book.authors.length === 0) return 'Chưa rõ tác giả'
  return book.authors
    .map((a) => a.role === 'author' ? a.name : `${a.name} (${AUTHOR_ROLES[a.role] ?? a.role})`)
    .join(', ')
}
