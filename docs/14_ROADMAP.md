# 14 · Lộ trình và danh sách task

Sản phẩm đích là chatbot Bát Tự gồm ba khối: **kho tri thức** lấy từ sách
([05](05_DOCUMENT_PIPELINE.md), [06](06_KNOWLEDGE_MODEL.md), [07](07_RAG_ENGINE.md)),
**engine tính lá số** độc lập ([08](08_BAZI_ENGINE.md)) và **LLM suy luận** trên facts,
rules và nguồn đã kiểm ([09](09_AI_REASONING.md)). Theo [ADR-21](15_ARCHITECTURE_DECISIONS.md#adr-21-chi-tiết),
kho tri thức được xây trước; lá số và chat đi sau nhưng vẫn thuộc phạm vi release.

Đây là nguồn duy nhất cho thứ tự và trạng thái task. Mã `T0xx` ở các tài liệu
khác tra tại bảng cuối file này.

## Trạng thái hiện tại

- T001 ✅ bảo toàn đầu vào (hash RAR/PDF, `legacy/bazi` immutable).
- T057 ✅ cấu trúc kho tri thức: inspector chỉ đọc ([`scripts/inspect_corpus.py`](../scripts/inspect_corpus.py)),
  Compose tối giản PostgreSQL/Redis/inspector, doctor tách `dev`/`deploy`.
- T002 ⏳ toolchain đã khóa, Compose đã build; còn smoke foundation trên Ubuntu 22.04
  thật (`scripts/dev doctor --target deploy`). Chi tiết ở decision log của 15.
- T003 ✅ backend foundation: app factory, typed config, request ID, JSON log có
  redaction, Problem Details, `/health/live` và `/health/ready` (chạy trên Windows dev;
  chưa có Compose service API).
- T004 ✅ migrations M001–M003 (identity, thư viện, tài liệu/chunk/release) với ràng buộc ở
  DB; 26 integration tests trên PostgreSQL thật.
- T005 ✅ migrations M004–M007 (tri thức, lá số, chat, jobs/vận hành), vòng đời duyệt ép ở
  DB, registry tham chiếu đa hình, seed chỉ taxonomy; 26 integration tests.
- T006 ✅ auth: Argon2id, session cookie + CSRF + Origin guard, giới hạn đăng nhập, roles,
  RLS chạy bằng login runtime (M008), chặn mất admin cuối, CLI bootstrap; tests API + RLS.
- T007 ✅ ObjectStore local + S3 (boto3), content-addressed, staging atomic, range, chặn
  traversal, xóa có kiểm tham chiếu; contract tests trên local và S3 (moto).
- T008 ✅ API contracts nền: DTO/envelope/problem có kiểu, `x-permission`, snapshot
  `contracts/openapi.json` có test, If-Match/ETag (users, settings), Idempotency-Key, `/settings`.
  TS client chuyển sang T043.1 (ADR-21: chưa dựng frontend khi chưa có màn hình thật).
- T009 ✅ catalog sách/tác giả/phiên bản/quyền, batch + upload từng tệp (magic bytes, DOCX an
  toàn, giới hạn kích thước, dedupe kể cả đồng thời, idempotency), job + outbox khi có profile;
  thêm bảng `ingestion_batch_items` (M009).
- T010 ✅ queue bền trong PostgreSQL: lease + fencing token, compute/persist tách, retry jitter,
  cancel, outbox + dedupe, watchdog/reconciler, Celery chỉ là tín hiệu; smoke thật
  outbox → Redis → Celery worker → DB.
- T011 ✅ extraction native bằng PDFium (ADR-22): block theo font/màu, bbox sau rotation,
  phân loại trang, nhãn trang, ba sách audit đủ 613 trang, 0 U+FFFD; stage validate/extract.
- T012 ✅ OCR Tesseract theo trang scan/vùng ảnh, giới hạn pixel/timeout/tài nguyên, không
  ghi đè native, timeout → review; image `app`/`test` có Tesseract, service worker/watchdog.
- T013 ✅ DOCX: text + anchor từ XML, bản dựng LibreOffice có font cố định, định vị đoạn
  (96% exact trên DOCX thật), fallback anchor không bịa trang; DOCX mới → version/generation mới.
- T014 ✅ chuẩn hóa + offset UTF-16, vai trò block/heading/lớp người nói, cây section, xác minh
  nhãn trang, review item theo lý do, 9 trang mẫu đối chiếu bằng mắt. Còn chờ: hiệu chỉnh ngưỡng
  bằng trang gán nhãn của chuyên gia (gộp vào T025.1).
- T015 ✅ chunking theo section/speaker, bảng/mệnh lệ nguyên khối, overlap, provenance từng ký tự,
  định danh chunk ổn định, chủ đề đề xuất.
- T016 ✅ registry embedding profile/collection, provider openai_compatible + fixture offline,
  stage embed (lexical FTS + vector theo lô, không nhân bản, tái dùng theo hash).
- T017 ✅ sửa trang thành revision mới (If-Match + idempotency), generation gia tăng tái dùng
  chunk/vector, gộp bản sửa khi rebuild còn chờ, flag `SOURCE_CHANGED` theo ký tự bị sửa,
  API impact; kèm sửa lỗi tiêu đề "Chương N: …" bị đọc thành hàng lá số (parser v5).
- T018 ✅ niêm phong generation (manifest), publish có gate quyền/chất lượng/index/profile,
  xác nhận partial theo khoảng trang, release mới + đổi con trỏ nguyên tử, activate CAS,
  `auto_publish`; chặn gửi text ra embedding provider ngoài khi version chưa cho phép.
- T019 ✅ jobs API (list/chi tiết/sự kiện/retry/cancel) + `job_events` bền, reprocess giữ bản
  sửa, withdraw thu hồi ngay khỏi release active, review queue (accept/exclude/retry/dismiss
  kèm rebuild), GC object/blob mồ côi có thời gian ân hạn. K2 xong phần backend.
- T020 ✅ school/topic/method/concept/alias có revision và review (submit/return/approve/
  reject/revoke, base_revision → 412), tìm alias không dấu theo trường phái, trường phái của
  sách theo version/khoảng trang (M010) thành phân loại chunk theo generation.
- T021 ✅ stage `extract_candidates`: assertion draft từ câu quy tắc/định nghĩa có evidence
  đúng offset, chỉ trên trang có trường phái đã duyệt, không nhân bản qua rebuild; đo Tử
  Bình 241, Manh phái sơ cấp 223 candidate.
- T022 ✅ evidence do reviewer chọn, assertion/relation/rule draft có revision, DSL
  `bazi-rule/1` kiểm schema/kiểu/giới hạn + đánh giá ba trị một rule, fixture bắt buộc
  fired/not_matched/pending trước khi duyệt rule, gate nguồn/method/dependency.
- T023 ✅ parser lá số in trong sách (4 dạng, kiểm 60 Giáp Tý, Càn/Khôn tạo, đại vận) thành
  book case draft có evidence; case người dùng riêng tư; API cases + review. Đo: ~1.220 lá số
  trong 4 PDF.
- T024 ✅ ontology release từ concept/alias đã duyệt, publish ghim qua corpus release mới
  (không xử lý lại tài liệu), đồ thị impact xuôi, revoke đánh dấu stale analyses phụ thuộc
  (M011, chỉ số đếm qua RLS).
- T035 ✅ `POST /search`: phạm vi theo quyền/release, lọc trường phái/sách/topic/trang ngay
  trong truy vấn, lexical + vector + tiêu đề section trộn RRF, mở rộng alias có dấu; smoke 10
  câu seed: Recall@5 9/10, Recall@10 10/10.
- T036 ⏳ adapter reranker + fallback + chặn gửi ngoài, đóng gói evidence bundle, dataset/run
  đánh giá (recall/hit/nDCG/MRR/latency); baseline seed: hit@10 1,0, recall@20 0,87, MRR 0,70.
  Còn chờ: chọn model embedding/reranker thật trên Ubuntu với gold đã duyệt.
- T037 ✅ bundle evidence lưu phía server (M012), `POST /citations/resolve` kiểm tồn tại/span/
  quote/support, claim lỗi không bao giờ kèm nguồn, materialise evidence span cho citation.
- T038 ✅ adapter LLM `openai_compatible` (timeout, retry jitter, JSON mode, một lượt sửa
  schema) + fixture, giữ chỗ chi phí trước gọi với trần ngày dùng chung (M013), usage/
  model-profiles API. T038.1 smoke Gemma thật chờ máy Ubuntu.
- K4 xong phần làm được trên máy dev; chờ: T002/T036/T038.1 trên Ubuntu, T025.1 gold với
  chuyên gia.
- T043.1 ✅ `frontend/` Next.js 16 + TS client sinh từ OpenAPI (kiểm lệch snapshot), đăng
  nhập/CSRF/hết phiên, shell theo quyền, tổng quan, thư viện + chi tiết sách; Compose
  `api`/`frontend`/`gateway` (Caddy, chỉ loopback); 11 E2E Playwright trên stack thật.
- T046.1 ✅ màn tải sách (batch, tiến độ, thử lại từng tệp), jobs + nhật ký + hủy/thử lại,
  phiên bản (publish có xác nhận thiếu trang, thu hồi gõ tên), hàng đợi duyệt và trang duyệt
  ảnh + bbox + sửa khối + diff + rebase khi 412; API ảnh trang PNG, pipeline profiles (CLI
  tạo), review item theo id; 17 E2E trên stack thật.
- T052.1 ✅ backup nhất quán không chặn ghi (pg_dump trên snapshot đã export + blob theo
  địa chỉ nội dung + khóa GC), manifest kiểm sha256, `scripts/dev backup`. T053.1 ✅
  preflight + restore vào Compose project/volume mới, kiểm số dòng mọi bảng/blob/release;
  đã thử trọn vòng qua Compose trên máy dev. Mã hóa/retention/API thuộc T052/T053 đầy đủ.
- K5 xong phần làm được trên máy dev.
- T026–T028 ✅ engine lá số `backend/app/calc/` (tiết khí UTC, tứ trụ, policy giờ Tý/giờ
  Mặt Trời, khoảng bất định → biến thể, đại vận/lưu niên, âm lịch VN/CN, ChartFacts +
  hash). T029 ⏳ oracle độc lập VSOP87 (≤57 s mọi tiết 1900–2100), khớp lunar-python,
  hồi quy 32 lá số; còn bảng HKO và chuyên gia duyệt policy/bảng.
- T030 ✅ hồ sơ sinh + lá số: BirthInput mã hóa AES-GCM theo chủ sở hữu/bản ghi, facts bất
  biến (hash do DB kiểm), policy lưu DB khi dùng lần đầu và không được trôi, API có kiểu.
- T031–T034 ✅ rule engine: chạy ruleset có thứ tự/phụ thuộc/ngân sách/trace/conflict,
  `cycle_at` + `query.as_of`, ruleset chụp đóng băng + kích hoạt CAS, analysis lưu trace +
  dependencies, stale khi đổi ruleset/thu hồi rule, đánh giá lại có diff. Rule mệnh lý thật
  vẫn chờ chuyên gia.
- T039–T041 ✅ suy luận ba chế độ (orchestrator cố định, validator claim, câu trả lời tất
  định khi chưa có/lỗi mô hình), hội thoại nhiều lượt (cửa sổ nhớ, tìm, xóa), SSE phát lại
  + hủy; worker `reasoner` (M014).
- T044 ✅ UI lá số (`/charts`, `/charts/new`, `/charts/[id]`): lỗi engine đúng ô (giờ không
  tồn tại/lặp do DST, ngày âm), trụ giờ để trống khi không biết giờ, vận/lưu niên, trace.
- T045 ✅ UI chat (`/chat`): hội thoại tìm/xóa, ngữ cảnh chế độ/lá số/trường phái/phương pháp
  (If-Match), SSE hiện tiến độ và claim đã kiểm, hủy, trích dẫn mở trang nguồn; mở từ lá số.
- T047 ✅ UI quản trị tri thức (`/knowledge/terms|concepts|assertions|rules|rulesets`, `/cases`):
  tạo/sửa thành bản nháp mới có lý do, duyệt tách khỏi lưu (checklist cho luận điểm/quy tắc/ca),
  thu hồi xem trước ảnh hưởng, kiểm DSL + fixture, dựng/kích hoạt bộ quy tắc CAS.
- T048 ✅ UI đánh giá (`/evaluation`: bộ dữ liệu, câu hỏi, duyệt bộ, chạy, câu trượt, so sánh
  lần chạy; nhãn fixture), cài đặt (`/settings`: cá nhân, mô hình thử/dùng, hệ thống + ngân
  sách, người dùng, bản kho/ontology) và panel quản trị trên tổng quan.
- T042 ✅ contract/client hoàn chỉnh: tên schema duy nhất (không còn `backend__…` trong
  client TS), header `Idempotency-Key`/`If-Match` khai báo trên đúng route đọc chúng (test đối
  chiếu mã nguồn endpoint), ví dụ success/failure sinh từ schema cho mọi body/response và được
  kiểm khớp schema; frontend gửi header qua `params.header` có kiểu; unit test mọi URL
  `/api/v1` trong frontend (kể cả SSE, upload, ảnh trang) có trong contract.
- T049 ✅ xóa dữ liệu cá nhân (tự xóa/admin xóa, tùy chọn xóa tài khoản, hàm DB xóa cứng theo
  đồ thị FK, ledger áp lại khi restore, test canary toàn DB) + chống prompt injection (dấu
  phân cách không giả được, `reasoning-2`, test SEC04 có mutation check); xóa hồ sơ sinh xóa
  trắng bản mã ngay.
- T050 (harness) ✅: chiến lược lexical/vector/hybrid/+rerank trên cùng release, page@1,
  rò trường phái, no-answer precision/recall, ngưỡng release, so baseline + hồi quy, lịch sử
  run qua API, CLI `evaluate` làm cổng CI. Số đo thật chờ gold duyệt (T025) + model (T036).
- T051 ✅ (phần máy dev): metrics + cảnh báo vận hành (M016, `/operations/metrics`, UI),
  `scripts/bench.py` PERF01–PERF03 trên DB tạm; số đo tổng hợp ghi ở docs/13. Chờ: đo trên
  Ubuntu với OCR/model thật, 1.000 tài liệu, PERF05.
- T052 ✅ backup mã hóa AES-256-GCM theo khối (khóa riêng `BACKUP_ENCRYPTION_KEY`), lưu giữ
  7 ngày + 4 tuần, ghi nhận vào `backups` + `GET /operations/backups`; T053 ✅ kiểm tra sau
  restore theo runbook, `scripts/dev drill` (diễn tập trên máy dev qua Compose, gỡ sạch).
- T054 ✅ (phần viết + công cụ): README runbook Ubuntu (cài lần đầu, backup hằng ngày,
  cập nhật có kiểm migration + quay lại, restore/diễn tập, theo dõi); `scripts/dev migrate`
  (status; upgrade chỉ khi có backup < 24 h) và `bootstrap`; doctor deploy đòi đủ khóa
  production. Chạy thật trên Ubuntu chờ T002.
- T055 ✅ (phần máy dev): quét IDOR sinh từ contract, test log không lộ dữ liệu, test header
  bảo mật; ma trận SEC01–SEC07 ở docs/13. Sửa: analyses của lá số người khác → 404, log
  không còn thông điệp exception và URL của httpx.
- T056 ⛔: bảng trạng thái tám kịch bản ở docs/13 — release candidate chưa nghiệm thu; chặn
  bởi T002 (Ubuntu), T025 (gold), T029/T033 (chuyên gia), T036 (model thật).
- Cải tiến sau K7 (18/10/2026): luận lá số theo quy tắc trên trang lá số, trích dẫn mở đúng
  đoạn, trang Tra cứu + giới hạn sách trong chat, phản hồi câu trả lời (M017), checklist
  khởi động, chia sẻ sách và gán trường phái trên UI — T043/T046 ✅.
- Việc kế tiếp: những gì cần môi trường Ubuntu, chuyên gia và mô hình thật (xem trên).
- **RAG pilot (21/10/2026, chủ dự án chốt, thay T036/T038.1 cho giai đoạn này):**
  - Đã có trong code:
    - OCR SenOCR-Vi.
    - `chunker-3`, chia chunk cha/con, kèm `chunk_meta` và tóm tắt Qwen cho mỗi cha.
    - Embedding và reranker Jina trên CPU.
    - Trộn hybrid 0,8/0,2.
    - `POST /ask` và chat research mode chạy trên pipeline mới.
    - `scripts/rag_eval.py` chạy 20 câu trong `test_questions.txt` rồi publish lên trang `/judge`, nơi người chấm vào bằng mật khẩu chung.
    - Qwen đề xuất quy tắc nguyên văn cho chuyên gia duyệt.
  - Quyết định và số đo: decision log ở 15.
  - Mục tiêu ngắn hạn: người chấm cho điểm, từ đó biết cần sửa OCR, chunk, truy xuất hay sinh câu trả lời.

## Các giai đoạn

| Mốc | Tasks | Kết quả kiểm tra được |
|---|---|---|
| K0 Cấu trúc + corpus | T001, T057 | Nguồn được bảo toàn; kiểm kê 7 file/815 trang |
| K1 Foundation Ubuntu | T002 → T003–T008 | Runtime, migrations, auth, ObjectStore, API nền chạy thật |
| **K2 Kho tài liệu** | T009–T019 | Upload → native/OCR/DOCX → review → chunk/embed → publish; pilot rồi mở rộng |
| **K3 Tri thức có cấu trúc** | T020–T025 | Concept/alias theo trường phái, assertions/cases có nguồn, gold ≥70 câu; không auto-approve |
| **K4 Tra cứu (RAG)** | T035–T038 | Hybrid + rerank + citation validator, adapter Gemma llama.cpp; số đo trên gold |
| K5 UI kho và vận hành | T043.1, T046.1, T052.1, T053.1 | Library/jobs/review dùng API thật; backup/restore kho trước khi dùng lâu dài |
| K6 Lá số và luận giải | T026–T034, T039–T045, T047–T048 | Oracle lịch, DSL rules, chat ba chế độ, UI còn lại |
| K7 Release đầy đủ | T049–T056 | Security, recovery, scale, tám kịch bản cuối ở [13](13_TEST_PLAN.md) |

**Mốc "kho tri thức dùng được"** = hết K4: nhập được sách mới không sửa code, review
và sửa OCR có revision, publish atomic, tìm kiếm có lọc trường phái/sách trả
evidence mở đúng trang, đo Recall@20/nDCG@10/citation trên gold đã duyệt.

## Kế hoạch xây kho tri thức (K2–K4)

Corpus thực và cách dùng từng nguồn: [05 · Corpus hiện tại](05_DOCUMENT_PIPELINE.md#corpus-hiện-tại).

1. **Pilot (T011, T014):** 30–60 trang gán nhãn bằng mắt text/bảng/mixed, gồm sơ cấp
   tr.16–22, 30–31, cao cấp tr.5/30, Tử Bình tr.26–34/77 và mẫu Trích Thiên Tủy.
   Thêm fixture scan/rotation; native extraction tốt không chứng minh OCR scan tốt.
2. **Nguồn PDF (T011–T012):** native trước, OCR chỉ trang/vùng thiếu chữ. Lưu
   raw/blocks/bbox/normalized map; edition/SHA, school/method, section và speaker.
   Bảng trụ/case liền mạch; kinh văn/bình chú tách nhưng liên kết; lớp chưa biết
   là `unknown/review_required`.
3. **DOCX (T013):** review 80 bảng, metadata và đoạn dịch/bình chú; locator XML rồi
   canonical PDF bằng renderer/fonts pin. Không giả số trang Word ổn định.
4. **Chunk/index (T015–T016):** thử section-aware 350–700 tokens, overlap 60–100 theo
   tokenizer thật; giữ điều kiện/ngoại lệ, case và bảng. Parent-child cho đoạn lớn,
   mọi child có source spans. FTS simple/unaccent/trgm trước, vector theo
   profile/version (ADR-16/17).
5. **Tri thức (T020–T024):** concept/alias có scope trường phái, assertions có speaker
   layer, cases từ sách; mọi candidate do máy sinh là draft chờ reviewer.
6. **Gold (T025.1 → T025):** ≥60 câu gốc (20 sơ cấp, 15 cao cấp, 15 Tử Bình, 10
   no-answer/cross-school) + 10 Trích Thiên Tủy thành ≥70. DOCX có tập riêng sau
   duyệt. Split theo section/case; CASE Markdown là adversarial candidate, không
   gold mặc định. Không dùng câu trả lời mẫu vừa làm context vừa làm gold.
7. **Retrieval (T035–T037):** quyền/scope/release → lexical/vector → RRF → rerank →
   evidence có locator → citation validation. Kiểm search độc lập trước LLM; so
   lexical/vector/hybrid/rerank trên cùng release theo gate ở [07](07_RAG_ENGINE.md#benchmark-retrievalanswer).
8. **LLM (T038.1):** Gemma qua llama.cpp chỉ sinh câu trả lời/đề xuất candidates sau
   khi search và citation đã có kiểm thử. Embedding là model riêng (ADR-16), chạy
   CPU/batch nếu VRAM đã dùng cho Gemma. Sách là untrusted evidence, không là
   system instruction hay quyền approve.

Chưa chọn model/context/chunk cuối cùng khi chưa đo recall và tài nguyên Ubuntu.

## Subtask tách sớm

Task cha chỉ hoàn thành khi đạt nghiệm thu gốc.

- **T038.1** llama.cpp config/timeout/model ID: sau T008. T038 đầy đủ (budget, mocks,
  usage, no-provider) sau T024.
- **T025.1** soạn ≥70 câu và relevant spans, kèm 30–60 trang gán nhãn quality để hiệu chỉnh
  ngưỡng T014: sau T014. T025 đầy đủ sau T024 và chuyên
  gia duyệt gold.
- **T043.1** shell/auth/library navigation + sinh TS client từ `contracts/openapi.json`:
  sau T006 + T008. T043 đầy đủ sau T042.
- **T046.1** library/upload/jobs/OCR review: sau T043.1 + T019, test upload → review →
  publish, 412/forbidden. T046 đầy đủ sau T045.
- **T052.1** backup DB/objects/checksums: sau T019. **T053.1** restore kho trên volumes
  mới: sau T052.1. T052/T053 đầy đủ giữ gates gốc.

## Phụ thuộc cần chú ý

- Calculation T026 chỉ cần T008, không cần sách; oracle T029 thu thập song song được.
- Rules T031 cần ontology T024 và facts T030. Reasoning T039 cần T034, T037, T038.
- UI chức năng cần contract đầy đủ T042; không ghi UI done trước backend thật.
- Security test theo module làm ngay trong từng task, không đợi T049.
- Ba PDF là dữ liệu kiểm thử, không là prerequisite của foundation/chart/DSL unit tests.
  Fixture synthetic gắn `synthetic_test`, không hiện như tri thức đã duyệt.

## Quy tắc làm task

Mỗi task: đọc tiêu chí ở tài liệu chủ sở hữu, chạy tests liên quan, commit với
message ghi task ID + tests đã chạy + kết quả, rồi cập nhật trạng thái bảng dưới.
Task bị chặn ghi `⛔` kèm blocker thực tế; chọn task khác đã đủ phụ thuộc. Không
bỏ yêu cầu cốt lõi để giữ bảng xanh. Quyết định kỹ thuật mới ghi vào decision log
của [15](15_ARCHITECTURE_DECISIONS.md#decision-log).

Cần chuyên gia: T025 duyệt gold/span/speaker; T029 lịch/policy; T033 rules từ sách
và ngoại lệ; T050 kiểm semantic support mẫu. Agent chuẩn bị fixtures/diff đầy đủ
trước khi trình duyệt.

## Danh sách task

✅ xong · ⏳ đang làm/chờ gate · ⛔ bị chặn · trống = chưa bắt đầu.

| ID | Task | Mốc | Trạng thái |
|---|---|---|---|
| T001 | Bảo toàn đầu vào và kiểm tra repository | K0 | ✅ |
| T057 | Cấu trúc kho tri thức và kế hoạch RAG | K0 | ✅ |
| T002 | Khóa toolchain, giấy phép và hạ tầng Compose | K1 | ⏳ smoke Ubuntu |
| T003 | Backend foundation và logging | K1 | ✅ |
| T004 | Migrations storage và document schema | K1 | ✅ |
| T005 | Migrations knowledge, chart, chat và jobs | K1 | ✅ |
| T006 | Auth, roles, RLS và admin bootstrap | K1 | ✅ |
| T007 | ObjectStore local và S3 adapters | K1 | ✅ |
| T008 | API contracts nền và client skeleton | K1 | ✅ (TS client → T043.1) |
| T009 | Catalog, upload batch và dedupe | K2 | ✅ |
| T010 | Durable queue, outbox, lease và retry | K2 | ✅ |
| T011 | Inspector và native PDF extraction | K2 | ✅ |
| T012 | OCR sandbox theo trang/vùng | K2 | ✅ |
| T013 | DOCX extraction và canonical rendering | K2 | ✅ |
| T014 | Unicode, cấu trúc và quality review | K2 | ✅ (hiệu chỉnh ngưỡng → T025.1) |
| T015 | Semantic chunking và provenance | K2 | ✅ |
| T016 | Embedding/index staging và model registry | K2 | ✅ |
| T017 | Sửa OCR incremental và impact | K2 | ✅ |
| T018 | Publication và active corpus release | K2 | ✅ |
| T019 | Reprocess, withdrawal, GC và jobs API | K2 | ✅ |
| T020 | Trường phái, phương pháp, concept và aliases | K3 | ✅ |
| T021 | Trích xuất candidates từ nguồn | K3 | ✅ |
| T022 | Duyệt assertions/rules và relations | K3 | ✅ |
| T023 | Kho mệnh lệ và structured chart từ sách | K3 | ✅ |
| T024 | Ontology releases và dependency impact graph | K3 | ✅ |
| T025 | Tập gold retrieval và chuyên môn | K3 | |
| T035 | Hybrid candidate retrieval và filters | K4 | ✅ |
| T036 | Embedding/reranker benchmark và context packing | K4 | ⏳ |
| T037 | Citation resolver và validator | K4 | ✅ |
| T038 | LLM adapters, cost reservation và mocks | K4 | ✅ |
| T026 | Adapter Calculation Engine và schema facts | K6 | ✅ |
| T027 | Timezone và giờ Mặt Trời | K6 | ✅ |
| T028 | Tiết khí, ngày Tý và chu kỳ vận | K6 | ✅ |
| T029 | Oracle độc lập và regression calculation | K6 | ⏳ chờ HKO + chuyên gia |
| T030 | Profiles/charts persistence và API | K6 | ✅ |
| T031 | DSL validator và typed interpreter | K6 | ✅ |
| T032 | Rule DAG, exceptions và conflict trace | K6 | ✅ |
| T033 | Rule approval gates và immutable rulesets | K6 | ✅ (rule thật chờ chuyên gia) |
| T034 | Re-evaluation và stale analysis tracking | K6 | ✅ |
| T039 | Reasoning orchestration cho ba modes | K6 | ✅ |
| T040 | Multi-turn conversations và search/delete | K6 | ✅ |
| T041 | SSE validated claims và cancellation | K6 | ✅ |
| T042 | API integration và generated client hoàn chỉnh | K6 | ✅ |
| T043 | Frontend shell, auth, navigation và empty states | K5/K6 | ✅ |
| T044 | Giao diện lập/xem/lưu lá số | K6 | ✅ |
| T045 | Chat UI, nguồn và so sánh | K6 | ✅ |
| T046 | Library upload/jobs/OCR review dashboard | K5/K6 | ✅ |
| T047 | Knowledge/rules/cases admin UI | K6 | ✅ |
| T048 | Evaluation/settings/dashboard UI | K6 | ✅ |
| T049 | Security hardening và privacy deletion | K7 | ✅ |
| T050 | Evaluation harness và quality regression | K7 | harness ✅; số đo chờ T025/T036 |
| T051 | Benchmark throughput, storage và observability | K7 | ✅ dev; số đo Ubuntu chờ T002/T036 |
| T052 | Backup service và CLI | K5/K7 | ✅ |
| T053 | Restore drill và disaster recovery | K5/K7 | ✅ dev; đo RTO trên Ubuntu chờ T002 |
| T054 | Windows dev/Ubuntu deployment runbook và update/migration checks | K7 | ✅ runbook + công cụ; chạy Ubuntu chờ T002 |
| T055 | Tích hợp hồi phục và test bảo mật cuối | K7 | ✅ dev; pentest ngoài chưa có |
| T056 | Nghiệm thu tám kịch bản và bàn giao đầy đủ | K7 | ⛔ chờ T002/T025/T029/T033/T036 |

## Không nằm trong release

Native mobile, thanh toán, public hosting, multi-tenant thương mại, cluster phân tán.
S3 adapter, OCR scan, rule approval, case library, evaluation, backup và privacy
**nằm trong** release. Lịch ngoài capability đã kiểm chứng đi qua adapter + oracle,
không thay thế âm thầm.
