"""Load a reviewed term list into concepts and terms (docs/06 · Concept, term).

The list (``data/glossary_v1.json``) was reviewed outside the app, entry by entry,
so loading it records that review: every concept and alias is created as a draft
and approved through ``decisions.decide`` by a named reviewer, with the list
version as the reason. Nothing is approved without a review row and an audit log.

Each entry has one ``definition`` (what the concept is, what sets it apart, the scope that
matters; no quotations) and may keep ``notes`` from the earlier list (e.g. the image tables of
a stem). The concept's description is the definition, then the notes as a second paragraph.

Re-running is safe. A concept whose latest revision already has the same label
and description only gets its missing aliases; a changed label or description
becomes a new revision (the seed Can/Chi/Ngũ Hành concepts get their reviewed
description this way and keep their Hán aliases).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..documents.text import fold, nfc
from . import decisions, ontology

GLOSSARY = Path(__file__).parent / 'data' / 'glossary_v1.json'


@dataclass
class Report:
    version: str
    created: int = 0
    revised: int = 0
    unchanged: int = 0
    aliases_added: int = 0
    missing_schools: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {'version': self.version, 'concepts_created': self.created,
                'concepts_revised': self.revised, 'concepts_unchanged': self.unchanged,
                'aliases_added': self.aliases_added, 'missing_schools': self.missing_schools}


def read(path: Path = GLOSSARY) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _approve(conn: Connection, principal: Principal, kind: str, entity_id, revision: int,
             reason: str) -> None:
    decisions.decide(conn, principal, kind, entity_id, 'approve', revision, reason, None)


def _wanted_aliases(entry: dict) -> list[tuple[str, str, str]]:
    """(form, language, alias_kind) beyond the canonical label, without repeats."""
    seen = {(fold(entry['label']), 'vi')}
    wanted = []
    for form, language, kind in ([(a, 'vi', 'same_concept') for a in entry['aliases']]
                                 + [(h, 'zh', 'translation_variant') for h in entry['han']]):
        form = nfc(form).strip()
        if form and (fold(form), language) not in seen:
            seen.add((fold(form), language))
            wanted.append((form, language, kind))
    return wanted


def _add_aliases(conn: Connection, principal: Principal, concept_id, entry: dict,
                 reason: str) -> int:
    present = {(fold(t['form']), t['language']) for t in ontology.get_concept(conn, concept_id)['terms']
               if t['state'] in ontology.LIVE}
    added = 0
    for form, language, kind in _wanted_aliases(entry):
        if (fold(form), language) in present:
            continue
        term = ontology.create_term(conn, concept_id, form, language, kind)
        _approve(conn, principal, 'term', term['id'], 1, reason)
        present.add((fold(form), language))
        added += 1
    # Aliases carried into a new revision stay drafts unless approved before; approve only
    # the ones this list names, never someone else's unreviewed draft.
    named = {(fold(f), lang) for f, lang, _ in _wanted_aliases(entry)}
    for term in ontology.get_concept(conn, concept_id)['terms']:
        if term['state'] == 'draft' and (term['form_folded'], term['language']) in named:
            _approve(conn, principal, 'term', term['id'], 1, reason)
    return added


def description(entry: dict) -> str:
    """Definition, then ``Ghi chú: <notes>``; a list without definitions uses its description."""
    main = nfc(entry.get('definition') or entry.get('description') or '').strip()
    notes = nfc(entry.get('notes') or '').strip()
    return f'{main}\n\nGhi chú: {notes}' if notes and notes != main else main


def load(conn: Connection, principal: Principal, glossary: dict) -> Report:
    report = Report(glossary['version'])
    reason = f"Danh sách thuật ngữ {glossary['version']} đã duyệt ngày {glossary['reviewed']}"
    schools = {s['key']: s['id'] for s in ontology.list_schools(conn)}
    for entry in glossary['concepts']:
        school_id = schools.get(entry['school'])
        if school_id is None:
            if entry['school'] not in report.missing_schools:
                report.missing_schools.append(entry['school'])
            continue
        latest = conn.execute(text(
            'SELECT id, revision, label, description, state FROM concepts'
            ' WHERE school_id = :s AND canonical_key = :k ORDER BY revision DESC LIMIT 1'),
            {'s': school_id, 'k': entry['key']}).mappings().first()
        label, text_ = nfc(entry['label']).strip(), description(entry)
        same = (latest is not None
                and (latest['label'], latest['description']) == (label, text_))
        if latest is None:
            concept = ontology.create_concept(conn, school_id, entry['key'], label, text_)
            _approve(conn, principal, 'concept', concept['id'], 1, reason)
            report.created += 1
        elif same and latest['state'] == 'approved':
            concept = {'id': latest['id']}
            report.unchanged += 1
        elif same and latest['state'] in ('draft', 'in_review'):
            concept = {'id': latest['id']}
            _approve(conn, principal, 'concept', latest['id'], latest['revision'], reason)
            report.revised += 1
        else:
            concept = ontology.revise_concept(conn, latest['id'], latest['revision'], label, text_)
            _approve(conn, principal, 'concept', concept['id'], concept['revision'], reason)
            report.revised += 1
        report.aliases_added += _add_aliases(conn, principal, concept['id'], entry, reason)
    return report
