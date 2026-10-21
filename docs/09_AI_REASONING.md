# 09 · AI Reasoning và hội thoại

## Chế độ và orchestration

| Mode | Dữ liệu bắt buộc | Luồng | Kết quả |
|---|---|---|---|
| research | câu hỏi + scope | resolve context → hybrid retrieve → evidence → answer validation | Giải thích, dẫn nguồn, khoảng thiếu |
| chart_analysis | chart revision + school/method | load facts → ruleset evaluation → targeted retrieval → supported interpretation | Facts, rules triggered, diễn giải, ngoại lệ |
| comparison | proposition + scopes | phân tách mệnh đề → retrieve từng scope → rule traces khi có chart → compare | Quan điểm ủng hộ/phản đối và phạm vi áp dụng |

Một orchestration state machine kiểm soát các bước, không agent tự chạy vô hạn. Run states: queued/running/waiting_provider/completed/failed/cancelled; persisted events có seq. Request tạo user message, pending assistant message và run trong một transaction; worker reasoning xử lý, không giữ HTTP POST chờ model. Chart engine local không phụ thuộc provider.

## Tool interfaces do server kiểm soát

- `get_chart_facts(chart_id)` → ChartFacts+owner check; không cho tool tự tạo ngày sinh mới.
- `calculate_chart(birth_input, policy_id)` → facts chỉ khi user yêu cầu lập/đổi lá số và input đã xác nhận ở UI; không tự đổi active chart trong hội thoại.
- `search_knowledge(QuerySpec)` → EvidenceBundle theo user scope; tool không nhận storage paths hay arbitrary SQL.
- `get_source_span(evidence_id, context_blocks<=2)` → đoạn nguồn thuộc run, quyền được kiểm lại.
- `evaluate_rules(chart_id, ruleset_id, method_id)` → RuleTrace deterministic; server kiểm ruleset scope.
- `find_cases(query, school_ids, max_results<=5)` → approved/private-owned cases và provenance.

Tối đa 8 tool calls/run, tối đa 2 retrieval refinements, timeout provider mặc định 60s/call và run cap 180s (cấu hình); tokens/cost reserved trước gọi. Tool errors typed có retryable, không đưa stack trace/secret vào model. Schema malformed thử sửa một lần, sau đó fail an toàn.

## Answer contract

`Answer`: status (`supported|partial|insufficient_evidence|empty_corpus|provider_not_configured`), mode, summary, claims, disagreements, limitations, follow_up_questions, citations, trace_ref.

`Claim`: id, text, kind (`calculation|rule_result|source_statement|interpretation|limitation`), school_id nullable, method_id nullable, time_scope nullable, fact_paths[], rule_trace_ids[], evidence_ids[], support_status (`validated|needs_review|insufficient`), inference_level (`direct|conditional|interpretive`), unresolved_exceptions[]. Mọi material source/interpretation claim phải có evidence; calculation dùng fact path + engine manifest thay vì nguồn sách. “validated” là đã qua kiểm tra hỗ trợ của hệ thống, không là chứng minh Bát Tự đúng khoa học.

LLM structured output không được tự định các fact_paths/trace IDs ngoài allowlist run. Validator kiểm schema, ownership, sources, school, contradicted fact values, unsupported health/finance wording và citation. Không hiển thị xác suất “95% đúng vận mệnh”; có thể hiển thị độ đầy đủ bằng chứng định tính và lý do.

## Multi-turn memory

Conversation có active chart revision, mode, selected schools/methods/books. Mỗi run ghim context snapshot và message sequence, không đọc setting đang thay đổi giữa run. Summary memory là nội dung không tin cậy, có provenance message IDs; giữ last 6 turns + summary trong token budget khởi đầu. User đổi chart → ghi context_changed event; không mang facts chart cũ sang mới. Chọn school mới → lọc lại, không lấy kiến thức summary school cũ làm nguồn.

Lưu/tìm/xóa conversation bằng DB. Search message text có owner filter, không gửi toàn bộ lịch sử cho provider. Delete conversation cancel runs và xóa content/claims/citations/events theo policy; audit giữ metadata tối thiểu không text. Rename/star do user; không cần AI.

## Streaming không phát tán câu trả lời chưa kiểm nguồn

SSE stream tiến độ (`run.started`, `tool.started`, `tool.completed`, `retrieval.ready`) ngay; model text thô được buffer. Sau khi từng claim hoàn chỉnh validate, phát `answer.claim`; khi toàn answer hoàn thành phát `answer.completed` với canonical payload. Đây là streaming các đoạn đã kiểm, có thể chậm hơn token streaming nhưng tránh citation giả xuất hiện rồi bị rút lại.

Event IDs `{run_id}:{seq}`, seq unique tăng dần; client reconnect `Last-Event-ID`, server replay từ durable `run_events` cho owner. Không chạy lại model khi reconnect. Nếu event retention hết, trả 410 với URL fetch final run; client fetch final answer. Heartbeat 15s không lưu DB; proxy tắt buffering. Cancel idempotent, status cancelled; provider có thể tiếp tục tính phí sau cancel nên usage phải reconcile. Disconnect không tự cancel trừ cấu hình explicit.

## Thiếu nguồn, xung đột và an toàn diễn giải

Corpus trống: vẫn xem facts/tra cứu cấu trúc tính toán, research trả hướng dẫn nhập sách; không trích dẫn trí nhớ LLM như đã đọc sách. Có nguồn mà chưa rule approved: trình bày tài liệu và facts, báo chưa có quy tắc đủ điều kiện; không tạo rule dùng tạm trong lượt đó.

Conflict: output chia theo school và speaker, dẫn luận cứ/ngoại lệ; không kết luận một phía “thắng” nếu không có tiêu chí người dùng. Health/finance/future: phrasing theo truyền thống và điều kiện, không khẳng định mắc bệnh/chắc chắn gặp tai nạn/khuyến nghị giao dịch từ lá số. Không biến câu chuyện bệnh trong mệnh lệ thành chẩn đoán người dùng.

## Provider adapters, privacy, budget

Interfaces `LLMProvider.generate_structured/stream`, `EmbeddingProvider.embed_batch`, `Reranker.rerank`; capabilities có schema support, tokenization, dimensions, pricing config version. Retry có jitter và idempotency nếu provider hỗ trợ, không giả provider nào cũng có. Mock provider phục vụ contract/E2E offline, `is_fixture=true` không được xuất hiện dưới nhãn AI thật ở production.

Settings lưu secret environment **reference**, model identifier/revision, context limit, timeout, concurrency, daily currency budget. Đặt cost reservation trong DB transaction trước gọi, tránh hai job cùng vượt trần; usage tokens actual/estimate và error costs. Không log full birth input, chat hoặc API key mặc định. Xuất telemetry chỉ bật theo admin consent.

Đã triển khai (T038, `backend/app/llm/`, M013): LLM active là profile `llm` bật mới nhất (`POST /model-profiles/{id}/activate` tắt các profile cùng loại). `openai_compatible` gọi `POST {base_url}/chat/completions` (llama.cpp/Gemma, vLLM, API ngoài) với model, timeout, `max_retries` (jitter đầy đủ, chỉ cho timeout/429/5xx; 4xx thất bại ngay) và `json_mode` (`json_schema` gửi schema pydantic, `json_object`, `none`); output có schema được kiểm, sai thì đúng một lượt sửa rồi `SCHEMA_INVALID`. `fixture-scripted` trả lời offline theo `config.replies` cho test/E2E, bị từ chối ở production. Profile không khai `locality: local` là bên ngoài: `may_send_book_text` chặn gửi text sách của version chưa cho phép. Ngân sách: trước mỗi lần gọi giữ chỗ chi phí tối đa (token ước tính + toàn bộ `max_tokens` theo giá profile) trong transaction riêng đã commit, dưới khóa theo profile, sau khi kiểm `daily_budget` dùng chung (tổng mọi người dùng qua hàm SECURITY DEFINER `bazi_usage_totals` chỉ trả số) — hai lời gọi đồng thời không thể cùng vượt trần (test với hai luồng); giữ chỗ tự hết hạn sau 10 phút; xong thì ghi token thật + chi phí thật, lỗi thì giải phóng. Không có model → 503 `PROVIDER_NOT_CONFIGURED`; vượt trần → 429 `BUDGET_EXCEEDED`. Smoke Gemma thật (model ID, context, JSON) là T038.1, chờ máy Ubuntu.

Đã triển khai (T039–T041, `backend/app/reasoning/`, `chat/`, `api/chat.py`, M014): orchestrator cố định theo chế độ — research: tìm trong phạm vi hội thoại → gói bằng chứng; chart_analysis: facts lá số (của chủ) → ruleset active của trường phái/phương pháp đã chọn (chưa có → ghi giới hạn, không tạo rule tạm) → tìm có mục tiêu; comparison: mỗi trường phái một lượt tìm, gộp một gói. Tối đa 8 tool/run, mỗi bước là sự kiện bền `{run_id}:{seq}`; hủy được kiểm giữa các bước. Mô hình chỉ thấy fact path đã liệt kê, rule đã kích hoạt, đoạn nguồn E# (lọc theo quyền gửi ra ngoài) và lịch sử như ngữ cảnh không tin cậy (`reasoning-2`: đoạn nguồn, lịch sử và câu hỏi nằm giữa dấu <<<…>>> không thể giả, kèm quy tắc không làm theo chỉ thị trong đó); trả `DraftAnswer` JSON. Validator: calculation phải dùng fact path có thật, rule_result phải là rule đã fired, source/interpretation phải qua citation resolver (nguồn không đủ → loại; diễn giải hỗ trợ yếu → `needs_review`), lệch trường phái và lời khẳng định chắc chắn về sức khỏe/tiền/tương lai → `needs_review`; claim bị loại chỉ được đếm. Không có mô hình, mô hình lỗi, hoặc sách không được gửi ra ngoài → câu trả lời tất định từ dữ kiện, quy tắc và trích nguyên văn (status `provider_not_configured` hoặc ghi rõ lỗi); kho trống → `empty_corpus`. Worker `python -m backend.app.reasoning.worker` (service `reasoner`) lấy run qua hàm SECURITY DEFINER chỉ trả id + owner rồi làm việc dưới RLS của owner; run treo quá 10 phút → failed; sự kiện hết hạn sau 7 ngày. Hội thoại: đổi lá số/trường phái mở cửa sổ nhớ mới (không mang facts cũ); mỗi run ghim context, 6 lượt gần nhất, profile LLM và release; một run hoạt động mỗi hội thoại (409 `RUN_ACTIVE`); xóa hội thoại hủy run, xóa nội dung/claims/citations/sự kiện, chỉ giữ metadata. SSE phát lại từ `Last-Event-ID` không chạy lại mô hình, heartbeat 15 s, dừng ở sự kiện kết thúc; sự kiện đã hết hạn → 410 kèm đường dẫn run.

## Answering harness (`backend/app/answering`, quy tắc trả lời bước 3–8)

Một câu hỏi đi qua: chặn câu hỏi rủi ro (sinh tử, bệnh, tai nạn, ly hôn ở tương lai → từ chối, không gọi model) → dữ kiện lá số tính bằng bảng (`calc/pillar_facts`) → danh sách ý cần biết → vòng bằng chứng → phân tích theo trường phái → tổng hợp → kiểm từng nhận định.

- **Ý cần biết:** câu hỏi chính; khái niệm chỉ cho thuật ngữ có trong glossary đã duyệt (so khớp có dấu, từ hai âm tiết, bỏ Can/Chi, tên trường phái và khung nền như Đại vận, Nhật chủ); ý phụ do model tách (①, bỏ qua với câu ngắn một ý); khi có lá số: B3 vượng suy và B4 dụng thần (tìm trong Tử Bình), B5 tố công (Manh phái), B7 cho các vận được hỏi (cả hai trường phái).
- **Vòng bằng chứng** (tối đa 7): tìm theo từng ý (lọc trường phái), model chấm từng ý (đủ / một phần / thiếu / mâu thuẫn) kèm câu trích nguyên văn; code kiểm câu trích có thật trong đoạn, không có thì không tính; ý còn thiếu được model viết truy vấn mới (④). Dừng sớm khi đủ hết, không có đoạn mới, hai vòng liền không tiến triển, hoặc hết ngân sách thời gian (`time_budget_s`, mặc định không giới hạn).
- **Phân tích theo trường phái:** mỗi trường phái một lần gọi, chỉ với bằng chứng của trường phái đó và dữ kiện lá số.
- **Tổng hợp:** nhận định ngắn kèm nguồn `[P#]` hoặc `F` (dữ kiện lá số); câu hỏi nêu một trường phái thì có thêm 1–2 nhận định "góc nhìn khác"; B6 ghi giống/khác. Code bỏ nhận định không nguồn, nguồn không có trong bằng chứng, độ phủ từ dưới `min_support`, hoặc khẳng định rủi ro; không còn nhận định chính thì "không đủ căn cứ". Câu trả lời do code dựng từ các nhận định còn lại, kèm phần "Chưa đủ căn cứ trong sách" và danh sách nguồn.
- **Vết:** mỗi bước, vòng, truy vấn, đoạn đã xem, câu trích được nhận/bị loại, lý do dừng và số lần gọi model nằm trong `Result.trace`.
- **Cổng:** `ports.Model` (Qwen qua `adapters.QwenModel`: JSON schema, thinking tắt trừ các bước được bật, bóc `<think>`, sửa JSON một lần) và `ports.Retriever` (`adapters.RagRetriever`: truy xuất RAG pilot không có bước sinh). Chạy bộ câu hỏi: `python -m backend.app.answering.run test_questions.txt --as <email>` → `.artifacts/answering/run-*.json` và `.md`.

