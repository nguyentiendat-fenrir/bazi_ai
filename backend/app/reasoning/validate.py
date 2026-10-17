"""From a model's draft to a validated Answer (docs/09 · Answer contract, Thiếu nguồn).

Every claim is checked against what the run handed over:

* calculation — every fact path must be one the run listed (a path the facts have);
* rule_result — every rule key must have fired in this run's analysis;
* source_statement / interpretation — every handle must be in the run's evidence
  bundle and pass the citation resolver (existence, span, hash; lexical support).
  A source statement without support is dropped; an interpretation with weak support
  is kept as ``needs_review``;
* certainty wording about health, money or the future marks the claim ``needs_review``.

Dropped claims are counted, never shown. Model ``limitation`` claims become limitations.
"""
from __future__ import annotations

import re

from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..retrieval.citations import resolve
from .answer import Answer, Citation, Claim, DraftAnswer

# Absolute or numeric certainty the reasoning contract forbids (docs/09 · an toàn diễn giải).
RISKY = re.compile(
    r'(chắc chắn|100\s*%|\d+\s*%|xác suất|tuyệt đối|không thể tránh|nhất định sẽ|'
    r'chắc chắn sẽ|sẽ chết|mắc bệnh|bị bệnh|ung thư|nên mua|nên bán|nên đầu tư|đầu tư vào|'
    r'cổ phiếu|tiền ảo)', re.IGNORECASE)


def _citations(resolved: dict) -> list[Citation]:
    return [Citation(handle=c['evidence_id'], evidence_span_ids=c['evidence_span_ids'],
                     book_id=c['book_id'], book_title=c['book_title'],
                     edition_label=c['edition_label'], section_title=c['section_title'],
                     speaker_layer=c['speaker_layer'], pages=c['pages'],
                     printed_pages=c['printed_pages'], quote=c['quote'], support=c['support'],
                     viewer=c['viewer']) for c in resolved['citations']]


def validate(conn: Connection, principal: Principal, draft: DraftAnswer, *, mode: str,
             bundle_id: str | None, groups: dict[str, dict], fact_paths: dict[str, object],
             fired: dict[str, dict], method_key: str | None, trace_ref: dict) -> Answer:
    sourced = [(i, c) for i, c in enumerate(draft.claims)
               if c.kind in ('source_statement', 'interpretation') and c.evidence
               and all(h in groups for h in c.evidence)]
    verdicts: dict[int, dict] = {}
    if sourced and bundle_id:
        result = resolve(conn, principal, bundle_id,
                         [{'text': c.text, 'evidence_ids': c.evidence} for _, c in sourced])
        verdicts = {i: r for (i, _), r in zip(sourced, result['claims'])}

    claims: list[Claim] = []
    limitations = list(draft.limitations)
    rejected = 0
    numbering: dict[int, str] = {}
    for index, draft_claim in enumerate(draft.claims):
        exceptions: list[str] = []
        citations: list[Citation] = []
        trace_ids: list[str] = []
        status = 'validated'
        if draft_claim.kind == 'limitation':
            limitations.append(draft_claim.text)
            continue
        if draft_claim.kind == 'calculation':
            if not draft_claim.fact_paths or any(p not in fact_paths for p in draft_claim.fact_paths):
                rejected += 1
                continue
        elif draft_claim.kind == 'rule_result':
            if not draft_claim.rule_keys or any(k not in fired for k in draft_claim.rule_keys):
                rejected += 1
                continue
            trace_ids = [fired[k]['rule_revision_id'] for k in draft_claim.rule_keys]
        else:
            verdict = verdicts.get(index)
            if verdict is None or verdict['status'] == 'invalid':
                rejected += 1
                continue
            if verdict['status'] == 'insufficient_evidence':
                if draft_claim.kind == 'source_statement':
                    rejected += 1
                    continue
                status = 'needs_review'
                exceptions.append('low_lexical_support')
            elif verdict['status'] == 'weak':
                status = 'needs_review'
                exceptions.append('weak_support')
            citations = _citations(verdict)
            schools = {groups[h].get('school_key') for h in draft_claim.evidence} - {None}
            if draft_claim.school_key and schools and draft_claim.school_key not in schools:
                status = 'needs_review'
                exceptions.append('school_mismatch')
        if RISKY.search(draft_claim.text):
            status = 'needs_review'
            exceptions.append('certainty_wording')
        numbering[index] = f'c{len(claims) + 1}'
        claims.append(Claim(
            id=numbering[index], text=draft_claim.text, kind=draft_claim.kind,
            school_key=draft_claim.school_key, method_key=method_key,
            time_scope=draft_claim.time_scope, fact_paths=draft_claim.fact_paths,
            rule_trace_ids=trace_ids, citations=citations, support_status=status,
            inference_level=draft_claim.inference_level, unresolved_exceptions=exceptions))

    disagreements = []
    for item in draft.disagreements:
        positions = [{'school_key': p.school_key,
                      'claim_ids': [numbering[i] for i in p.claim_indexes if i in numbering]}
                     for p in item.positions]
        if sum(1 for p in positions if p['claim_ids']) >= 2:
            disagreements.append({'topic': item.topic, 'positions': positions})
    if rejected:
        limitations.append(f'{rejected} nhận định của mô hình bị loại vì không kiểm được nguồn'
                           ' hoặc dữ kiện.')
    if not claims:
        status = 'insufficient_evidence'
    elif rejected or any(c.support_status != 'validated' for c in claims):
        status = 'partial'
    else:
        status = 'supported'
    return Answer(status=status, mode=mode, summary=draft.summary, claims=claims,
                  disagreements=disagreements, limitations=limitations,
                  follow_up_questions=draft.follow_up_questions, rejected_claims=rejected,
                  trace_ref=trace_ref)
