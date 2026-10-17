# 07 · Hybrid RAG

Tài liệu này đặc tả truy xuất trên corpus đã publish. Corpus thực ở
[05](05_DOCUMENT_PIPELINE.md#corpus-hiện-tại); thứ tự xây kho và các đợt nhập ở
[14](14_ROADMAP.md#kế-hoạch-xây-kho-tri-thức-k2k4). LLM sinh trả lời là Gemma qua
llama.cpp ([12](12_SECURITY_OPERATIONS.md#kết-nối-gemma-llamacpp)), chỉ sau khi
search và citation đã có kiểm thử.

## Index đã triển khai (T016)

`backend/app/retrieval`: `model_profiles` embedding bất biến, định danh bằng hash của provider/model/revision/dimension/config/secret_ref; config không được chứa khóa dạng secret, `secret_ref` chỉ nhận `EMBEDDING_API_KEY`/`LLM_API_KEY`. Collection vật lý `embeddings_<model>_<dim>_<hash8>` (`vector(D)` cố định nên vector sai số chiều bị DB từ chối) do lệnh owner `python -m backend.app.cli embedding-profile … --provision [--ann-index]` tạo và cấp quyền cho `bazi_runtime`; HNSW chỉ tạo khi được yêu cầu. Provider: `openai_compatible` (`POST {base_url}/embeddings`, timeout/429/5xx → retry unit, 4xx/sai số chiều → lỗi vĩnh viễn) và `fixture-hashing` (offline, không ngữ nghĩa, bị cấm ở production). Stage `embed` theo lô 64 chunk: `search_entries` (`fts-simple-1`: `to_tsvector('simple')` trên NFC và bản bỏ dấu, trgm bản bỏ dấu) cho mọi chunk; vector chỉ khi profile của pipeline có collection `ready`, bỏ qua chunk đã có vector và tái dùng vector của chunk cùng content hash (không gọi provider). Không có collection → chỉ lexical, job vẫn thành công. Model thật (e5/bge-m3) chọn ở T036 sau benchmark.

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

Tập gold khởi đầu ≥70 câu: 20 Manh sơ cấp, 15 cao cấp, 15 Tử Bình, 10 Trích Thiên Tủy và 10 câu no-answer/cross-school. Chuyên gia gán relevant spans/rationale, grade 0/1/2 cho nDCG; split theo section/case để tránh câu paraphrase rò vào cả train/test. Bộ 12 seed cụ thể ở [13](13_TEST_PLAN.md#seed-retrieval-gold-bản-nháp-có-locator-đã-kiểm-tra) chỉ là điểm khởi đầu, không giả đã có đủ gold.

Đo Recall@20, nDCG@10, MRR@10, school leakage, no-answer precision/recall, citation existence, page accuracy, claim support, latency p50/p95, cost/query. So lexical-only/vector-only/hybrid/hybrid+rerank với cùng release. Ngưỡng nghiệm thu dự kiến: Recall@20 ≥0,90; nDCG@10 ≥0,75; valid citation IDs/page mapping=100%; human-supported material claims ≥95%; no school leakage trong restrictive filter=0. Ngưỡng chỉ là gate mục tiêu, chưa có số đo; chuyên gia phê duyệt gold trước release. Không dùng LLM judge làm oracle duy nhất.
