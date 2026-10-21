"""Which reviewed terms a question names (concept needs are made only for these)."""
from __future__ import annotations

from dataclasses import dataclass
import re

from ..documents.text import nfc
from ..knowledge.glossary import GLOSSARY, read

# Building blocks and names are never useful needs ("Giáp là gì", "Đại vận là gì", "Tử Bình là gì").
SKIP_PREFIXES = ('can.', 'chi.', 'ngu_hanh.')
SKIP_CATEGORIES = {'can_chi', 'khac', 'lop_loi', 'lich_phap'}
SKIP_LABELS = {'đại vận', 'lưu niên', 'tiểu vận', 'nhật chủ', 'bát tự', 'tứ trụ', 'thập thần'}
SCHOOL_OF = {'tu_binh': 'tu_binh', 'manh_phai': 'manh_phai', 'tu_tru': None}


@dataclass(frozen=True)
class Term:
    label: str
    key: str
    school: str | None
    form: str


# Old and new tone placement (hoả/hỏa, thuỷ/thủy) and common variant spellings.
_SPELLING = [(re.compile(rf'o{a}(?=\b)'), f'{b}a') for a, b in
             (('à', 'ò'), ('á', 'ó'), ('ả', 'ỏ'), ('ã', 'õ'), ('ạ', 'ọ'))] + \
            [(re.compile(rf'u{a}(?=\b)'), f'{b}y') for a, b in
             (('ỳ', 'ù'), ('ý', 'ú'), ('ỷ', 'ủ'), ('ỹ', 'ũ'), ('ỵ', 'ụ'))] + \
            [(re.compile(r'\btị\b'), 'tỵ'), (re.compile(r'\bkỉ\b'), 'kỷ'), (re.compile(r'\bquí\b'), 'quý'),
             (re.compile(r'\btỉ\b'), 'tỷ'), (re.compile(r'\bhỉ\b'), 'hỷ'), (re.compile(r'\bkị\b'), 'kỵ')]


def _key(text: str) -> str:
    """Lower case WITH diacritics: folding makes "không cần" match "không căn" (Vô căn)."""
    text = nfc(text).lower()
    for pattern, repl in _SPELLING:
        text = pattern.sub(repl, text)
    return ' '.join(re.findall(r'\w+', text))


class GlossaryIndex:
    """Longest-match lookup of reviewed labels and aliases of two or more syllables."""

    def __init__(self, concepts: list[dict]):
        self.forms: dict[str, list[Term]] = {}
        for c in concepts:
            if (c['key'].startswith(SKIP_PREFIXES) or c.get('category') in SKIP_CATEGORIES
                    or _key(c['label']) in SKIP_LABELS):
                continue
            for form in [c['label'], *c['aliases']]:
                form = nfc(form).strip()
                if len(form.split()) < 2:
                    continue          # one syllable ("Tài", "Mộ", "thể") matches ordinary words
                term = Term(c['label'], c['key'], SCHOOL_OF.get(c['school']), form)
                self.forms.setdefault(_key(form), []).append(term)
        self.longest = max((len(k.split()) for k in self.forms), default=0)

    @classmethod
    def load(cls, path=GLOSSARY) -> 'GlossaryIndex':
        return cls(read(path)['concepts'])

    def find(self, text: str) -> list[Term]:
        """Terms named in ``text``, longest match first, each concept once, in text order."""
        words = _key(text).split()
        found, seen, i = [], set(), 0
        while i < len(words):
            for size in range(min(self.longest, len(words) - i), 1, -1):
                hits = self.forms.get(' '.join(words[i:i + size]))
                if hits:
                    for t in hits:
                        if (t.key, t.school) not in seen:
                            seen.add((t.key, t.school))
                            found.append(t)
                    i += size
                    break
            else:
                i += 1
        return found
