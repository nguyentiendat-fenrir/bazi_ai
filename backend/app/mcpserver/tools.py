"""The "bazi-rag" MCP server: four read-only tools over the RAG and the answering harness."""
from __future__ import annotations

from typing import Annotated, Any, Literal

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from ..answering.harness import Config, Harness
from ..answering.ports import SCHOOL_LABELS
from ..calc import pillar_facts
from ..documents.text import nfc
from ..knowledge import sources
from .backend import Backend, Unavailable

INSTRUCTIONS = (
    'Thư viện sách Bát Tự (Tử Bình Chân Thuyên, Trích Thiên Tủy, Manh phái) có dẫn nguồn.'
    ' search_books: tìm đoạn sách; answer_question: trả lời có kiểm nguồn từng nhận định;'
    ' chart_facts: dữ kiện lá số tính bằng bảng từ tứ trụ viết sẵn; lookup_terms: thuật ngữ'
    ' đã duyệt theo trường phái. Tử Bình và Manh phái là hai trường phái riêng, không trộn.'
    ' Hợp chỉ là hợp, không xét hóa.')
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                            openWorldHint=False)
School = Literal['tu_binh', 'manh_phai']
TEXT_LIMIT = 4000
SOURCES_PER_TERM = 3


async def _run(fn, *args):
    try:
        return await anyio.to_thread.run_sync(fn, *args)
    except Unavailable as exc:
        raise ToolError(str(exc)) from None


def build_server(backend: Backend, settings) -> FastMCP:
    server = FastMCP(
        'bazi-rag', instructions=INSTRUCTIONS, stateless_http=True, json_response=True,
        streamable_http_path='/',
        # The API's own bearer check and origin guard protect the route; the gateway sets Host.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def search_books(
            query: Annotated[str, Field(min_length=1, max_length=500, description='câu hoặc cụm từ cần tìm')],
            school: Annotated[School | None, Field(description='chỉ tìm trong sách của trường phái này')] = None,
            k: Annotated[int, Field(ge=1, le=10)] = 5) -> dict[str, Any]:
        """Tìm đoạn sách liên quan (dense + BM25, rerank, trả đoạn cha). Mỗi đoạn có sách, trang,
        trường phái; dùng để trích dẫn."""
        def go():
            passages = backend.retriever().search(nfc(query), school, k)
            return {'query': query, 'school': school, 'passages': [
                {'id': p.pid, 'book': p.book, 'pages': p.pages, 'school': p.school,
                 'header': p.header, 'text': p.text[:TEXT_LIMIT]} for p in passages]}
        return await _run(go)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def answer_question(
            question: Annotated[str, Field(min_length=1, max_length=4000)],
            max_rounds: Annotated[int, Field(ge=1, le=7)] = settings.mcp_answer_rounds,
            include_trace: bool = False) -> dict[str, Any]:
        """Trả lời câu hỏi Bát Tự chỉ từ sách: tách ý, tìm bằng chứng nhiều vòng, kiểm câu trích,
        phân tích lá số theo từng trường phái nếu câu hỏi có tứ trụ, rồi kiểm nguồn từng nhận
        định. Câu hỏi về sinh tử, bệnh tật, ly hôn trong tương lai bị từ chối."""
        def go():
            model = backend.model()
            try:
                config = Config(max_rounds=max_rounds, time_budget_s=settings.mcp_time_budget)
                result = Harness(model, backend.retriever(), backend.glossary, config).answer(question)
            finally:
                close = getattr(model, 'close', None)
                if close:
                    close()
            out = result.to_dict()
            if not include_trace:
                out.pop('trace')
            out['needs'] = [{k: n[k] for k in ('id', 'kind', 'school', 'text', 'status')}
                            for n in out['needs']]
            return out
        return await _run(go)

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def chart_facts(
            text: Annotated[str, Field(min_length=1, max_length=4000,
                                       description='câu hỏi hoặc đoạn có tứ trụ, ví dụ "Lá số nam: Mậu Ngọ'
                                                   ' – Ất Mão – Nhâm Tý – Canh Tý. Đại vận: …"')]) -> dict[str, Any]:
        """Dữ kiện lá số tính bằng bảng tra (không phải trích sách): nhật chủ, nguyệt lệnh, thập
        thần, tàng can, trường sinh, Lộc, Kình Dương, Thiên Mã, hợp xung hình hại phá, ám hợp, tự
        hợp, quan hệ với từng đại vận, cảnh báo nếu lá số không thể có."""
        chart = pillar_facts.find_chart(text)
        if chart is None:
            return {'found': False, 'message': 'Không tìm thấy đủ bốn trụ can chi trong văn bản.'}
        facts = pillar_facts.facts(chart)
        return {'found': True, 'text': pillar_facts.render(facts), 'warnings': facts['warnings'],
                'pillars': {p['position']: [p['stem'], p['branch']] for p in facts['pillars']},
                'luck': [[v['stem'], v['branch']] for v in facts['luck']], 'sex': facts['sex']}

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def lookup_terms(
            text: Annotated[str, Field(min_length=1, max_length=2000,
                                       description='thuật ngữ, hoặc một câu có nhắc thuật ngữ')],
            school: Annotated[School | None, Field(description='chỉ lấy khái niệm của trường phái này')] = None
    ) -> dict[str, Any]:
        """Thuật ngữ đã duyệt (glossary-1): tên chuẩn, trường phái, cách viết khác, mô tả, nguồn.
        Mỗi nguồn: tên sách, trang (trang in nếu có), câu neo, đoạn văn quanh nó và link mở trang
        trong thư viện của máy này (matched=not_found nếu máy này chưa có sách đó).
        Cùng một chữ có thể là hai khái niệm khác nhau ở Tử Bình và Manh phái."""
        wanted = nfc(text).strip().lower()
        by_label = [c for c in backend.concepts if c['label'].lower() == wanted
                    or wanted in (a.lower() for a in c['aliases'])]
        keys = {(t.key, t.school) for t in backend.glossary.find(text)}
        found = by_label + [c for c in backend.concepts
                            if (c['key'], {'tu_tru': None}.get(c['school'], c['school'])) in keys
                            and c not in by_label]
        if school:
            found = [c for c in found if c['school'] in (school, 'tu_tru')]
        found = found[:10]
        refs = [s for c in found for s in c['sources'][:SOURCES_PER_TERM]]
        try:
            opened = iter(await _run(backend.sources, refs))
        except Exception:       # sources are an extra: no library here still gives book + page
            opened = iter([sources.unresolved(r) for r in refs])
        return {'terms': [{'label': c['label'], 'school': SCHOOL_LABELS.get(
            None if c['school'] == 'tu_tru' else c['school']), 'school_key': c['school'],
            'category': c['category'], 'aliases': c['aliases'], 'definition': c.get('definition') or c.get('description', ''), 'notes': c.get('notes', ''),
            'sources': [next(opened) for _ in c['sources'][:SOURCES_PER_TERM]]} for c in found]}

    return server
