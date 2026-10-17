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
- Việc kế tiếp: T008 API contracts; smoke T002 trên Ubuntu khi có máy.

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
- **T025.1** soạn ≥70 câu và relevant spans: sau T014. T025 đầy đủ sau T024 và chuyên
  gia duyệt gold.
- **T043.1** shell/auth/library navigation: sau T006 + T008. T043 đầy đủ sau T042.
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
| T008 | API contracts nền và client skeleton | K1 | |
| T009 | Catalog, upload batch và dedupe | K2 | |
| T010 | Durable queue, outbox, lease và retry | K2 | |
| T011 | Inspector và native PDF extraction | K2 | |
| T012 | OCR sandbox theo trang/vùng | K2 | |
| T013 | DOCX extraction và canonical rendering | K2 | |
| T014 | Unicode, cấu trúc và quality review | K2 | |
| T015 | Semantic chunking và provenance | K2 | |
| T016 | Embedding/index staging và model registry | K2 | |
| T017 | Sửa OCR incremental và impact | K2 | |
| T018 | Publication và active corpus release | K2 | |
| T019 | Reprocess, withdrawal, GC và jobs API | K2 | |
| T020 | Trường phái, phương pháp, concept và aliases | K3 | |
| T021 | Trích xuất candidates từ nguồn | K3 | |
| T022 | Duyệt assertions/rules và relations | K3 | |
| T023 | Kho mệnh lệ và structured chart từ sách | K3 | |
| T024 | Ontology releases và dependency impact graph | K3 | |
| T025 | Tập gold retrieval và chuyên môn | K3 | |
| T035 | Hybrid candidate retrieval và filters | K4 | |
| T036 | Embedding/reranker benchmark và context packing | K4 | |
| T037 | Citation resolver và validator | K4 | |
| T038 | LLM adapters, cost reservation và mocks | K4 | |
| T026 | Adapter Calculation Engine và schema facts | K6 | |
| T027 | Timezone và giờ Mặt Trời | K6 | |
| T028 | Tiết khí, ngày Tý và chu kỳ vận | K6 | |
| T029 | Oracle độc lập và regression calculation | K6 | |
| T030 | Profiles/charts persistence và API | K6 | |
| T031 | DSL validator và typed interpreter | K6 | |
| T032 | Rule DAG, exceptions và conflict trace | K6 | |
| T033 | Rule approval gates và immutable rulesets | K6 | |
| T034 | Re-evaluation và stale analysis tracking | K6 | |
| T039 | Reasoning orchestration cho ba modes | K6 | |
| T040 | Multi-turn conversations và search/delete | K6 | |
| T041 | SSE validated claims và cancellation | K6 | |
| T042 | API integration và generated client hoàn chỉnh | K6 | |
| T043 | Frontend shell, auth, navigation và empty states | K5/K6 | |
| T044 | Giao diện lập/xem/lưu lá số | K6 | |
| T045 | Chat UI, nguồn và so sánh | K6 | |
| T046 | Library upload/jobs/OCR review dashboard | K5/K6 | |
| T047 | Knowledge/rules/cases admin UI | K6 | |
| T048 | Evaluation/settings/dashboard UI | K6 | |
| T049 | Security hardening và privacy deletion | K7 | |
| T050 | Evaluation harness và quality regression | K7 | |
| T051 | Benchmark throughput, storage và observability | K7 | |
| T052 | Backup service và CLI | K5/K7 | |
| T053 | Restore drill và disaster recovery | K5/K7 | |
| T054 | Windows dev/Ubuntu deployment runbook và update/migration checks | K7 | |
| T055 | Tích hợp hồi phục và test bảo mật cuối | K7 | |
| T056 | Nghiệm thu tám kịch bản và bàn giao đầy đủ | K7 | |

## Không nằm trong release

Native mobile, thanh toán, public hosting, multi-tenant thương mại, cluster phân tán.
S3 adapter, OCR scan, rule approval, case library, evaluation, backup và privacy
**nằm trong** release. Lịch ngoài capability đã kiểm chứng đi qua adapter + oracle,
không thay thế âm thầm.
