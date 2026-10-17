# 07 · Hybrid RAG

## Kế hoạch theo corpus thực — T057 / ADR-21

Kiểm kê ngày 17/10/2026: quét text tất cả 815 trang PDF bằng pypdf 6.21.0, đọc
mở đầu/mục lục và cấu trúc DOCX/Markdown. Chưa thẩm định từng luận điểm, chưa OCR
hoặc benchmark RAG. Số ký tự pypdf không thay số đo PyMuPDF audit cũ.

| Nguồn | Đo thực tế | Cách dùng |
|---|---|---|
| Manh phái sơ cấp lý pháp | 292 trang; 286.986 ký tự | Pilot trước: Khách–Chủ, Thể–Dụng, Tố Công; giữ bảng trụ/mệnh lệ |
| Manh phái cao cấp — Đoàn Kiến Nghiệp | 181 trang; 195.516 ký tự | Ứng kỳ/Tượng pháp; review tr.5 ít chữ, ảnh tr.30 theo audit |
| Tử Bình Chân Thuyên bình chú | 140 trang; 449.136 ký tự | School riêng, nguyên tác Thẩm Hiếu Chiêm/bình chú Từ Nhạc Ngô; review màu và ảnh tr.77 |
| Trích Thiên tuỷ bình chú — Nhậm Thiết Tiều | 202 trang; 583.731 ký tự | Đối chiếu cổ thư; xác nhận author layers/edition, không tự gộp quan điểm |
| Tên Sách Chưa Đặt.docx | 1.773 đoạn XML; 80 bảng; 130.687 ký tự | Bản biên soạn Manh phái có bình chú cá nhân; draft chờ metadata/source layers |
| CASE_01_TAN_KIM_1992.md | 59.481 ký tự | Hồ sơ giả định, ứng viên case/evaluation; không nguồn sách/oracle |
| CASE_02_AT_MOC_1997.md | 62.479 ký tự | Kiểm tàng/thấu, thiếu căn, điều kiện chế Sát/tòng; giữ ngoài corpus chuẩn |

CASE nhắc `validate_cases.py` nhưng repo không có file đó. Các tuyên bố “đã kiểm”
trong CASE chưa được tái lập ở đây; cần đối chiếu trang PDF và nguồn liên kết.
Không giả nội dung web chưa nhập là nguồn có trong kho. Không dùng câu trả lời
mẫu vừa làm context vừa làm gold chấm chính nó.

### Các đợt nhập và gate

1. **Pilot:** 30–60 trang gán nhãn bằng mắt text/bảng/mixed, gồm sơ cấp tr.16–22,
   30–31, cao cấp tr.5/30, Tử Bình tr.26–34/77 và mẫu Trích Thiên Tủy. Thêm fixture
   scan/rotation; native extraction tốt không chứng minh OCR scan tốt.
2. **Nguồn:** native trước, OCR vùng cần thiết. Lưu raw/blocks/bbox/normalized map;
   edition/SHA, school/method, section và speaker. Bảng trụ/case liền mạch, kinh
   văn/bình chú tách nhưng liên kết; lớp chưa biết là unknown/review_required.
3. **DOCX:** review 80 bảng, metadata và đoạn dịch/bình chú; locator XML rồi
   canonical PDF bằng renderer/fonts pin. Không giả số trang Word ổn định.
4. **Chunk/index:** thử section-aware 350–700 tokens, overlap 60–100 theo tokenizer
   thật; giữ điều kiện/ngoại lệ, case và bảng. Parent-child cho đoạn lớn, mọi child
   có source spans. FTS simple/unaccent/trgm trước, vector theo profile/version;
   tham số cần benchmark, không coi là chất lượng đã đạt.
5. **Retrieval:** quyền/scope/release → lexical/vector → RRF → rerank → evidence
   có locator → Gemma llama.cpp → citation validation. Kiểm search độc lập trước
   LLM. Embedding riêng theo ADR-16, CPU/batch nếu VRAM đang dùng hết.
6. **Gold:** giữ ≥60 câu gốc (20 sơ cấp, 15 cao cấp, 15 Tử Bình, 10 no-answer /
   cross-school), thêm 10 Trích Thiên Tủy thành ≥70. DOCX có tập riêng sau duyệt.
   Split theo section/case; CASE là adversarial candidate cần reviewer, không
   gold mặc định. So lexical/vector/hybrid/rerank trên cùng release; gates bên dưới.

Gemma sinh câu trả lời/đề xuất candidates sau khi search và citation có kiểm thử.
Sách là untrusted evidence, không system instructions hoặc quyền approve. Chưa
chọn model/context/chunk cuối cùng khi chưa đo recall và tài nguyên Ubuntu.

## Request và bộ lọc

`QuerySpec`: query (1–4.000 ký tự), mode, school_ids, method_ids, book_version_ids, author_ids, topic_ids, concept_ids, rule_revision_ids, case_ids, section_ids, physical_page_range, top_k (1–30, mặc định 8). Caller principal và active corpus release do server gán; không tin release/quyền do LLM gửi. API cho `book_ids` và resolve thành versions published trong release. Filter được intersect, không union tùy tiện khi user chọn một nguồn cụ thể. Khi filter không có dữ liệu, báo empty_filters, không mở rộng sang sách khác mà không thông báo.

## Luồng tìm kiếm

1. NFC + whitespace cho query gốc; bản folded lower-case/unaccent/đ→d chỉ là trường tìm kiếm phụ. Giữ chữ Hán và dấu trong output. Term matcher longest exact phrases ưu tiên tên riêng/thuật ngữ; không tự đồng nhất Thể–Dụng/Dụng Thần.
2. Expansion tối đa 5 biến thể, từ aliases đã duyệt cùng school và concept. Query rewriting LLM optional, chỉ tạo query terms, không được đổi scope/ACL. Multi-turn resolver dùng active chart/topic và câu hỏi mới, giữ câu hỏi gốc trong log.
3. Lexical candidates: PostgreSQL FTS `simple` GIN trên NFC và folded text, phrase booster qua term IDs; `pg_trgm` cho typo/title/author. Không tuyên bố FTS simple là BM25 hoặc đã có Vietnamese word segmentation. Có thể thêm tokenizer adapter sau benchmark bằng ADR, không bắt buộc Elasticsearch.
4. Semantic candidates: embedding model profile của release, cosine distance, top 80 khởi đầu. Truy vấn chỉ generation/chunk membership hợp lệ, published + rights/ACL. Cần filter trước/đúng trong query; ANN có thể hụt recall với filter. Dùng iterative scan hoặc exact scan trên tập nhỏ (threshold đo T035); không bỏ filter để đủ top_k.
5. Weighted reciprocal rank fusion: `score = Σ weight_i/(60 + rank_i)`, rank bắt đầu 1; khởi đầu lexical=1, vector=1, thuật ngữ exact booster được log. Không cộng trực tiếp ts_rank với cosine.
6. Rerank top 40 bằng multilingual cross-encoder adapter, cùng query và đoạn ngắn trong token limit. Timeout thì fallback fused order, `degraded=reranker_unavailable`; không tự chuyển school. Reranker không quyết định facts hay nguồn hợp lệ.
7. Context packing: tối đa 8 evidence groups/~6.000 tokens mặc định; merge adjacent chunks cùng section/speaker có đủ source map, dedupe overlap, tối đa 3 groups/book trừ book-filter. Giữ exception và table/case trong cùng context; nếu bị cắt ghi truncated. Chừa token cho answer/tool schema. Trả contrast sources riêng khi Comparison.
8. EvidenceBundle gồm opaque evidence_id, chunk_revision/content hash, title/edition/author, school/method/speaker, section path, spans, excerpt, scores và flags. Chỉ backend tạo source IDs và URL viewer.

Các top_k/token/cutoff/model ở trên là profile khởi đầu, **không** là kết quả benchmark. Embedding candidate `multilingual-e5-base` (768d) và `bge-m3` (1024d) có revision/license review và benchmark tiếng Việt/Hán Việt; model thắng trở thành registry active. Reranker candidate multilingual BGE reranker phù hợp tài nguyên; không cần tải tất cả cùng lúc. API embeddings có thể dùng nếu quyền external_processing cho phép. Offline/failure lexical fallback được hiển thị rõ.

## Citation validation

Citation **existence**: evidence_id trong bundle của run, chủ sở hữu quyền còn hiệu lực, source version/generation/page revision tồn tại và không withdrawn. Citation **span**: offsets/bboxes hợp lệ, quote substring trùng normalized snapshot, hash khớp; bảng nhiều trang có nhiều spans. Citation **support**: assertion thật sự được nguồn hỗ trợ, không phải chỉ có vài từ giống nhau. Support checker kết hợp heuristics/model judge + human gold; không bảo đảm tuyệt đối semantic entailment bằng kiểm substring.

LLM tạo claims tham chiếu evidence_id, không gõ số trang tự do. Backend thay evidence_id bằng citation object sau validate. Claim nguồn sai trả lại một lần sửa; vẫn sai thì bỏ claim hoặc hiện insufficient_evidence. Không đưa invalid citation ra UI kể cả trong streaming draft. UI mở PDF physical page và highlight bbox; label hiển thị cả trang PDF và trang in nếu khác. Có nút xem surrounding section để tránh dẫn cắt nghĩa.

## Quyền, cache và không có dữ liệu

Retrieval cache key gồm query normalized, expansion/ontology version, corpus release, embedding/reranker profiles, filters, principal permission scope và visibility_epoch. Query logs mặc định redacted; có opt-in raw để debug, retention ngắn. Empty corpus trả `{status:"empty_corpus", hits:[]}` 200; filtered empty trả `no_match`; dependency offline trả `degraded` hoặc 503 có code, không nhầm với không có kiến thức.

Book withdrawal/xóa quyền invalidate epoch và kiểm lại trước trả answer; cache không là đường vòng đọc sách cấm. Chunks đã superseded vẫn đọc để citation lịch sử nếu không withdrawn, nhưng không lọt vào retrieval mới.

## Benchmark retrieval/answer

Tập gold khởi đầu ≥60 câu: 20 Manh sơ cấp, 15 cao cấp, 15 Tử Bình và 10 câu no-answer/cross-school. Chuyên gia gán relevant spans/rationale, grade 0/1/2 cho nDCG; split theo section/case để tránh câu paraphrase rò vào cả train/test. Bộ 12 seed cụ thể ở 13 chỉ là điểm khởi đầu, không giả đã có 60 gold.

Đo Recall@20, nDCG@10, MRR@10, school leakage, no-answer precision/recall, citation existence, page accuracy, claim support, latency p50/p95, cost/query. So lexical-only/vector-only/hybrid/hybrid+rerank với cùng release. Ngưỡng nghiệm thu dự kiến: Recall@20 ≥0,90; nDCG@10 ≥0,75; valid citation IDs/page mapping=100%; human-supported material claims ≥95%; no school leakage trong restrictive filter=0. Ngưỡng chỉ là gate mục tiêu, chưa có số đo; chuyên gia phê duyệt gold trước release. Không dùng LLM judge làm oracle duy nhất.
