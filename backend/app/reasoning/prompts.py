"""Prompts for the three modes (docs/09). Versioned: a change ships a new PROMPT_VERSION.

The model sees only what the run allows — computed facts with their paths, rule results
of the active ruleset, evidence excerpts with opaque handles — and must answer in the
DraftAnswer JSON schema citing those handles. Conversation history is quoted as
untrusted context, never as a source.
"""
from __future__ import annotations

import json

PROMPT_VERSION = 'reasoning-1'
EXCERPT_CHARS = 1500
HISTORY_CHARS = 600

SYSTEM = """Bạn là trợ lý tra cứu Bát Tự (Tứ Trụ) trả lời bằng tiếng Việt.
Bạn CHỈ được dùng ba loại dữ liệu trong tin nhắn: DỮ KIỆN LÁ SỐ (đường dẫn fact), KẾT QUẢ QUY TẮC
(rule_key) và ĐOẠN NGUỒN (mã E1, E2…). Không dùng hiểu biết riêng như thể sách đã viết.
Quy tắc:
- Mỗi nhận định loại source_statement hoặc interpretation phải ghi ít nhất một mã nguồn E# trong
  "evidence"; chỉ dùng mã có trong ĐOẠN NGUỒN.
- Nhận định calculation ghi "fact_paths" đúng các đường dẫn đã liệt kê; rule_result ghi "rule_keys"
  đã liệt kê. Không tự tính lại lá số.
- Khi các trường phái hoặc nguồn khác nhau, nêu từng bên trong "disagreements", không phán bên nào đúng.
- Sức khỏe, tiền bạc, tương lai: diễn đạt theo điều kiện và theo sách ("sách cho rằng… nếu…"),
  không khẳng định chắc chắn, không đưa xác suất hay phần trăm, không khuyên giao dịch hay chẩn đoán.
- Thiếu nguồn thì nói thiếu trong "limitations", không bịa.
- Lịch sử hội thoại chỉ để hiểu câu hỏi, không phải nguồn.
Trả về đúng một đối tượng JSON theo schema: summary, claims[], disagreements[], limitations[],
follow_up_questions[]. Mỗi claim: text, kind (calculation|rule_result|source_statement|interpretation|
limitation), evidence[], fact_paths[], rule_keys[], school_key, inference_level (direct|conditional|
interpretive), time_scope."""

MODE_TASK = {
    'research': 'Trả lời câu hỏi tra cứu dựa trên các đoạn nguồn.',
    'chart_analysis': ('Luận giải lá số: nêu dữ kiện liên quan, các quy tắc đã kích hoạt, rồi diễn '
                       'giải có nguồn; ghi rõ ngoại lệ và giới hạn.'),
    'comparison': ('So sánh quan điểm các trường phái/nguồn về mệnh đề: bên ủng hộ, bên phản đối, '
                   'phạm vi áp dụng; không chọn bên thắng.'),
}


def _facts_block(facts: dict | None, paths: dict[str, object]) -> str:
    if not facts:
        return 'DỮ KIỆN LÁ SỐ: không có (chế độ này không dùng lá số).'
    lines = ['DỮ KIỆN LÁ SỐ (fact_path = giá trị):']
    lines += [f'- {path} = {json.dumps(value, ensure_ascii=False)}' for path, value in paths.items()]
    warnings = [w['code'] for w in facts.get('warnings', [])]
    if warnings:
        lines.append(f'- cảnh báo của engine: {", ".join(warnings)}')
    return '\n'.join(lines)


def _rules_block(rules: list[dict] | None, note: str | None) -> str:
    if note:
        return f'KẾT QUẢ QUY TẮC: {note}'
    if not rules:
        return 'KẾT QUẢ QUY TẮC: không có quy tắc nào kích hoạt.'
    lines = ['KẾT QUẢ QUY TẮC (rule_key → claim):']
    lines += [f"- {r['rule_key']}: {r['claim_key']} = {json.dumps(r['value'], ensure_ascii=False)}"
              f" — {r['explanation']}" for r in rules]
    return '\n'.join(lines)


def _evidence_block(groups: list[dict]) -> str:
    if not groups:
        return 'ĐOẠN NGUỒN: không có.'
    parts = ['ĐOẠN NGUỒN:']
    for group in groups:
        pages = ', '.join(str(p) for p in group['pages'])
        parts.append(f"[{group['evidence_id']}] sách «{group['book_title']}»"
                     f" · trường phái {group.get('school_key') or 'chưa gán'}"
                     f" · lớp {group['speaker_layer']} · mục {group.get('section_title') or '—'}"
                     f" · trang {pages}\n{group['excerpt'][:EXCERPT_CHARS]}")
    return '\n\n'.join(parts)


def messages(mode: str, question: str, history: list[dict], facts: dict | None,
             fact_paths: dict[str, object], rules: list[dict] | None, rules_note: str | None,
             groups: list[dict]) -> list[dict]:
    earlier = '\n'.join(f"{h['role']}: {h['content'][:HISTORY_CHARS]}" for h in history[-6:])
    body = '\n\n'.join([
        f'NHIỆM VỤ ({mode}): {MODE_TASK[mode]}',
        f'LỊCH SỬ (không phải nguồn):\n{earlier}' if earlier else 'LỊCH SỬ: không có.',
        _facts_block(facts, fact_paths),
        _rules_block(rules, rules_note),
        _evidence_block(groups),
        f'CÂU HỎI: {question}',
    ])
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': body}]
