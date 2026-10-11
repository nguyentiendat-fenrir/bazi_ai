# TASKS · Triển khai tuần tự cho Codex

**Trạng thái ban đầu: 0/56 task triển khai đã hoàn thành.** Đây là kế hoạch xây ứng dụng sau khi nhận ZIP; audit Work không làm các task application tự thành hoàn tất. Thứ tự số là một topological order hợp lệ. Có thể thực hiện T026 sau T008 nếu cần mở nhánh tính lá số, nhưng mặc định cứ chạy T001→T056 để đơn giản. Không tự chạy nhiều agent hoặc các migration song song.

Mỗi task chỉ được `[x]` khi test chỉ định đã thực chạy pass và có `reports/tasks/Txxx.md` gồm commit, command, exit code, fixtures, giới hạn. Các lệnh test paths dưới đây là contract để Codex tạo, không tuyên bố đã có sẵn trong ZIP. Nếu task quá lớn, chia subtask Txxx.1…n trong cùng task, giữ dependencies và nghiệm thu cha; không cắt bỏ phạm vi.

Các task T016/T021 có thể dùng local embedding và fixture provider theo interface đã đặc tả; integration provider API thật/cost reservation hoàn thiện ở T038. Candidate extraction bằng model thật chỉ bật sau gate đó; không coi mock là kết quả đã nghiên cứu sách.

## Checklist

- [ ] T001 — Bảo toàn đầu vào và kiểm tra repository — **BLOCKED**, xem [báo cáo](reports/tasks/T001.md) và [issues](reports/tasks/T001/issues.md)
- [ ] T002 — Khóa toolchain, giấy phép và hạ tầng Compose
- [ ] T003 — Backend foundation và logging
- [ ] T004 — Migrations storage và document schema
- [ ] T005 — Migrations knowledge, chart, chat và jobs
- [ ] T006 — Auth, roles, RLS và admin bootstrap
- [ ] T007 — ObjectStore local và S3 adapters
- [ ] T008 — API contracts nền và client skeleton
- [ ] T009 — Catalog, upload batch và dedupe
- [ ] T010 — Durable queue, outbox, lease và retry
- [ ] T011 — Inspector và native PDF extraction
- [ ] T012 — OCR sandbox theo trang/vùng
- [ ] T013 — DOCX extraction và canonical rendering
- [ ] T014 — Unicode, cấu trúc và quality review
- [ ] T015 — Semantic chunking và provenance
- [ ] T016 — Embedding/index staging và model registry
- [ ] T017 — Sửa OCR incremental và impact
- [ ] T018 — Publication và active corpus release
- [ ] T019 — Reprocess, withdrawal, GC và jobs API
- [ ] T020 — Trường phái, phương pháp, concept và aliases
- [ ] T021 — Trích xuất candidates từ nguồn
- [ ] T022 — Duyệt assertions/rules và relations
- [ ] T023 — Kho mệnh lệ và structured chart từ sách
- [ ] T024 — Ontology releases và dependency impact graph
- [ ] T025 — Tập gold retrieval và chuyên môn
- [ ] T026 — Adapter Calculation Engine và schema facts
- [ ] T027 — Timezone và giờ Mặt Trời
- [ ] T028 — Tiết khí, ngày Tý và chu kỳ vận
- [ ] T029 — Oracle độc lập và regression calculation
- [ ] T030 — Profiles/charts persistence và API
- [ ] T031 — DSL validator và typed interpreter
- [ ] T032 — Rule DAG, exceptions và conflict trace
- [ ] T033 — Rule approval gates và immutable rulesets
- [ ] T034 — Re-evaluation và stale analysis tracking
- [ ] T035 — Hybrid candidate retrieval và filters
- [ ] T036 — Embedding/reranker benchmark và context packing
- [ ] T037 — Citation resolver và validator
- [ ] T038 — LLM adapters, cost reservation và mocks
- [ ] T039 — Reasoning orchestration cho ba modes
- [ ] T040 — Multi-turn conversations và search/delete
- [ ] T041 — SSE validated claims và cancellation
- [ ] T042 — API integration và generated client hoàn chỉnh
- [ ] T043 — Frontend shell, auth, navigation và empty states
- [ ] T044 — Giao diện lập/xem/lưu lá số
- [ ] T045 — Chat UI, nguồn và so sánh
- [ ] T046 — Library upload/jobs/OCR review dashboard
- [ ] T047 — Knowledge/rules/cases admin UI
- [ ] T048 — Evaluation/settings/dashboard UI
- [ ] T049 — Security hardening và privacy deletion
- [ ] T050 — Evaluation harness và quality regression
- [ ] T051 — Benchmark throughput, storage và observability
- [ ] T052 — Backup service và CLI
- [ ] T053 — Restore drill và disaster recovery
- [ ] T054 — Windows/WSL runbook và update/migration checks
- [ ] T055 — Tích hợp hồi phục và test bảo mật cuối
- [ ] T056 — Nghiệm thu tám kịch bản và bàn giao đầy đủ

## Chi tiết nhiệm vụ

### T001 · Bảo toàn đầu vào và kiểm tra repository

- **Mục tiêu:** Bảo toàn đầu vào và kiểm tra repository.
- **Dependencies:** Không; điểm bắt đầu.
- **File/module:** `scripts/verify_inputs.py; legacy/bazi; reports/tasks/T001.md`.
- **Công việc cụ thể:** Kiểm git/WSL/Docker và các file hiện có; hash RAR/PDF theo audit; liệt kê archive và giải nén an toàn source vào legacy, loại .venv/.git/cache; lưu manifest, không sửa source gốc.
- **API/schema contract:** 02; input hashes; không API/schema mới.
- **Test cần chạy:** `python scripts/verify_inputs.py --check; malicious archive path fixture`.
- **Tiêu chí nghiệm thu:** Hash đúng, source nguyên vẹn, missing inputs báo rõ; report không lộ dữ liệu cá nhân.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T001.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T002 · Khóa toolchain, giấy phép và hạ tầng Compose

- **Mục tiêu:** Khóa toolchain, giấy phép và hạ tầng Compose.
- **Dependencies:** T001.
- **File/module:** `pyproject.toml; uv.lock; frontend/package.json; frontend lock; infra/compose.yaml; .env.example`.
- **Công việc cụ thể:** Chốt compatibility stack baseline, licenses parsers/models, images digest; Compose mạng nội bộ/loopback/volumes/health; doctor script và resource profiles; không bật secrets mặc định.
- **API/schema contract:** 03,12,ADR01/03/12.
- **Test cần chạy:** `docker compose config; scripts/dev doctor; container smoke`.
- **Tiêu chí nghiệm thu:** Lock tái lập; no latest; gateway duy nhất cổng host; health xác định essential/degraded.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T002.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T003 · Backend foundation và logging

- **Mục tiêu:** Backend foundation và logging.
- **Dependencies:** T002.
- **File/module:** `backend/app/main.py; core/config.py; core/errors.py; tests/unit/test_core.py`.
- **Công việc cụ thể:** Tạo app factory, typed config/env refs, request ID, structured redaction logs, Problem Details, liveness/readiness interfaces; route không business logic.
- **API/schema contract:** 10 common response/error envelope.
- **Test cần chạy:** `pytest tests/unit/test_core.py`.
- **Tiêu chí nghiệm thu:** Invalid config fail rõ; exceptions không lộ key; request_id xuyên log/response.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T003.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T004 · Migrations storage và document schema

- **Mục tiêu:** Migrations storage và document schema.
- **Dependencies:** T003.
- **File/module:** `backend/migrations; models/documents.py; tests/integration/test_document_schema.py`.
- **Công việc cụ thể:** Triển khai nhóm M001–M003 và dependency tables cần thiết; extensions, objects/books/pages/revisions/generations/chunks/index registry; composite constraints.
- **API/schema contract:** 04 document data dictionary.
- **Test cần chạy:** `pytest tests/integration/test_document_schema.py; alembic upgrade head empty DB`.
- **Tiêu chí nghiệm thu:** PK/FK/unique/check fail đúng với invalid spans, duplicate generation membership; không chỉ test ORM.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T004.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T005 · Migrations knowledge, chart, chat và jobs

- **Mục tiêu:** Migrations knowledge, chart, chat và jobs.
- **Dependencies:** T004.
- **File/module:** `backend/migrations; models/knowledge.py; models/chat.py; models/jobs.py`.
- **Công việc cụ thể:** Bổ sung M004–M007, deferred FK cycle chat/messages, dependency registry triggers, evaluation/operations; seed chỉ ontology taxonomy.
- **API/schema contract:** 04 remaining dictionary; 06 lifecycles.
- **Test cần chạy:** `pytest tests/integration/test_schema_integrity.py; migration up/backward compatibility smoke`.
- **Tiêu chí nghiệm thu:** Mọi bảng API cần đều có; 0 approved fictitious rules; unknown FK targets bị từ chối.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T005.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T006 · Auth, roles, RLS và admin bootstrap

- **Mục tiêu:** Auth, roles, RLS và admin bootstrap.
- **Dependencies:** T005.
- **File/module:** `backend/app/auth; scripts/bootstrap_admin.py; migrations/rls; tests/api/test_auth.py`.
- **Công việc cụ thể:** Session hash/password Argon2id, login rate-limit, CSRF/Origin, principal DB session context, owner RLS, last-admin guard.
- **API/schema contract:** 10 auth/users; 04 RLS.
- **Test cần chạy:** `pytest tests/api/test_auth.py tests/integration/test_rls.py`.
- **Tiêu chí nghiệm thu:** Reader không xem private chart người khác; runtime không bypass RLS; không open registration.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T006.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T007 · ObjectStore local và S3 adapters

- **Mục tiêu:** ObjectStore local và S3 adapters.
- **Dependencies:** T006.
- **File/module:** `backend/app/storage; tests/integration/test_storage.py`.
- **Công việc cụ thể:** Implement stream put_if_absent/stat/get/delete/manifests; atomic staging→ready; checksum; path allowlist; S3 adapter cùng interface và stub/real endpoint contract tests.
- **API/schema contract:** 03 storage;04 objects;12 safe blobs.
- **Test cần chạy:** `pytest tests/integration/test_storage.py; S3-compatible test endpoint suite`.
- **Tiêu chí nghiệm thu:** Hai adapter roundtrip/checksum/range/no traversal; delete object còn references bị chặn.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T007.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T008 · API contracts nền và client skeleton

- **Mục tiêu:** API contracts nền và client skeleton.
- **Dependencies:** T007.
- **File/module:** `backend/app/api; contracts/openapi.json; frontend/src/lib/api; tests/api/test_contracts.py`.
- **Công việc cụ thể:** Xuất OpenAPI versioned schemas/envelopes/permissions/idempotency middleware; sinh TypeScript client skeleton; health/settings/users routes.
- **API/schema contract:** 10 common/auth/settings.
- **Test cần chạy:** `pytest tests/api/test_contracts.py; TS typecheck; OpenAPI diff`.
- **Tiêu chí nghiệm thu:** Typed errors/statuses đúng; stale If-Match và changed idempotency payload bị chặn.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T008.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T009 · Catalog, upload batch và dedupe

- **Mục tiêu:** Catalog, upload batch và dedupe.
- **Dependencies:** T008.
- **File/module:** `backend/app/documents/catalog.py; uploads.py; tests/api/test_uploads.py`.
- **Công việc cụ thể:** Books/authors/editions/rights, streaming upload từng file vào batch, format/size/hash check, duplicate report, metadata và ACL.
- **API/schema contract:** 10 books/uploads/batches;04 objects/books/access.
- **Test cần chạy:** `pytest tests/api/test_uploads.py`.
- **Tiêu chí nghiệm thu:** Same bytes concurrent không nhân objects; batch healthy files vẫn accepted khi file khác lỗi.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T009.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T010 · Durable queue, outbox, lease và retry

- **Mục tiêu:** Durable queue, outbox, lease và retry.
- **Dependencies:** T009.
- **File/module:** `backend/app/ingestion/queue.py; worker.py; outbox.py; watchdog.py`.
- **Công việc cụ thể:** Implement job/stage state machine, idempotency unit keys, fencing tokens, heartbeat/watchdog, cancellation và retry; operation_jobs dùng cùng lease service.
- **API/schema contract:** 05 states;04 jobs/outbox/operations;10 jobs.
- **Test cần chạy:** `pytest tests/integration/test_job_recovery.py`.
- **Tiêu chí nghiệm thu:** Kill worker ở 3 ranh giới ghi dữ liệu không mất published outputs/không duplicate; Redis restart recover từ DB.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T010.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T011 · Inspector và native PDF extraction

- **Mục tiêu:** Inspector và native PDF extraction.
- **Dependencies:** T010.
- **File/module:** `backend/app/ingestion/pdf_native.py; inspector.py; tests/fixtures/pdf`.
- **Công việc cụ thể:** Text/scan/mixed theo trang; Docling native backend/parser adapter; save raw text/layout/font/color/bbox và page labels candidates; không OCR toàn file mặc định.
- **API/schema contract:** 05 extract/locator;04 pages/blocks.
- **Test cần chạy:** `pytest tests/integration/test_pdf_native.py`.
- **Tiêu chí nghiệm thu:** Ba mẫu page count 613; native text giữ Unicode; blank page không bị false hard failure.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T011.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T012 · OCR sandbox theo trang/vùng

- **Mục tiêu:** OCR sandbox theo trang/vùng.
- **Dependencies:** T011.
- **File/module:** `backend/app/ingestion/ocr.py; infra/ocr.Dockerfile; tests/integration/test_ocr.py`.
- **Công việc cụ thể:** OCRmyPDF/Tesseract adapter, vie/eng/Hán khi cần, sandbox limits/no network/timeouts; merge regions không duplicate native text.
- **API/schema contract:** 05 OCR/quality;12 sandbox.
- **Test cần chạy:** `pytest tests/integration/test_ocr.py with scan/mixed/pixel bomb fixtures`.
- **Tiêu chí nghiệm thu:** Scan có source mapping, timeout ra review, healthy native text không bị ghi đè.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T012.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T013 · DOCX extraction và canonical rendering

- **Mục tiêu:** DOCX extraction và canonical rendering.
- **Dependencies:** T012.
- **File/module:** `backend/app/ingestion/docx.py; render.py; tests/fixtures/docx`.
- **Công việc cụ thể:** Parse paragraph/table anchors; reject unsafe relationships/zip bomb; pin LibreOffice/font; generate canonical PDF với render hash và anchor/page map.
- **API/schema contract:** 05 DOCX page_kind;04 page revisions.
- **Test cần chạy:** `pytest tests/integration/test_docx.py`.
- **Tiêu chí nghiệm thu:** Table/paragraph source mở đúng; render fail dùng anchor không bịa page; DOCX changes tạo generation mới.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T013.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T014 · Unicode, cấu trúc và quality review

- **Mục tiêu:** Unicode, cấu trúc và quality review.
- **Dependencies:** T013.
- **File/module:** `backend/app/ingestion/normalize.py; structure.py; quality.py`.
- **Công việc cụ thể:** NFC offset map, preserve raw, detect chapters/TOC/speaker layers; quality signals + manual gold calibration; printed labels verified workflow.
- **API/schema contract:** 05 quality/locator;06 author layers.
- **Test cần chạy:** `pytest tests/unit/test_normalization.py tests/integration/test_quality.py`.
- **Tiêu chí nghiệm thu:** UTF16/codepoint roundtrip, không đổi nghĩa thuật ngữ; review items có lý do; 9 visual samples đọc đúng.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T014.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T015 · Semantic chunking và provenance

- **Mục tiêu:** Semantic chunking và provenance.
- **Dependencies:** T014.
- **File/module:** `backend/app/ingestion/chunker.py; provenance.py`.
- **Công việc cụ thể:** Chunk theo section/speaker/paragraph, tables/cases bounded windows, overlap source map, stable identity; metadata classification proposed.
- **API/schema contract:** 05 chunks;04 chunks/spans/generation membership.
- **Test cần chạy:** `pytest tests/unit/test_chunker.py tests/integration/test_spans.py`.
- **Tiêu chí nghiệm thu:** Mọi ký tự source claim map được về trang/block; cross-page span đầy đủ; không trộn speaker.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T015.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T016 · Embedding/index staging và model registry

- **Mục tiêu:** Embedding/index staging và model registry.
- **Dependencies:** T015.
- **File/module:** `backend/app/retrieval/embedding.py; indexer.py; models.py`.
- **Công việc cụ thể:** Profile/dimension registry, physical collection provisioning an toàn, batch embed cache hash, lexical FTS/trgm entries, retries/budget hooks; mock offline.
- **API/schema contract:** 04 embedding collections;07 lexical/vector.
- **Test cần chạy:** `pytest tests/integration/test_indexing.py`.
- **Tiêu chí nghiệm thu:** Same profile/hash replay không duplicate; dimension/model mismatch reject; no secret/provider hardcode.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T016.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T017 · Sửa OCR incremental và impact

- **Mục tiêu:** Sửa OCR incremental và impact.
- **Dependencies:** T016.
- **File/module:** `backend/app/documents/corrections.py; ingestion/incremental.py`.
- **Công việc cụ thể:** Correction revision ETag; rebuild affected windows/sections, reuse unchanged chunks; evidence cũ immutable; impact sources/rules/cases.
- **API/schema contract:** 05 incremental;10 corrections/impact.
- **Test cần chạy:** `pytest tests/integration/test_corrections.py`.
- **Tiêu chí nghiệm thu:** Sửa một paragraph chỉ thay vùng cần thiết; heading change mở rộng đúng; old citations không drift.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T017.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T018 · Publication và active corpus release

- **Mục tiêu:** Publication và active corpus release.
- **Dependencies:** T017.
- **File/module:** `backend/app/ingestion/publish.py; documents/releases.py`.
- **Công việc cụ thể:** Atomic membership+pointer, quality/rights gates, partial coverage acknowledge, auto_publish accepted content, no autoapprove rules.
- **API/schema contract:** 04 corpus;05 publish;10 generations/publish.
- **Test cần chạy:** `pytest tests/integration/test_publication.py`.
- **Tiêu chí nghiệm thu:** Concurrent query chỉ thấy complete old/new snapshots; empty corpus 200; failed generation không đổi active.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T018.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T019 · Reprocess, withdrawal, GC và jobs API

- **Mục tiêu:** Reprocess, withdrawal, GC và jobs API.
- **Dependencies:** T018.
- **File/module:** `backend/app/ingestion/reprocess.py; gc.py; api/jobs.py`.
- **Công việc cụ thể:** Pipeline upgrades/new embedding cohort, pause/resume/retry endpoints, epoch withdrawal override, safe orphan GC, logs/counters.
- **API/schema contract:** 05 recovery/withdrawal;10 jobs/releases.
- **Test cần chạy:** `pytest tests/integration/test_reprocess.py tests/api/test_jobs.py`.
- **Tiêu chí nghiệm thu:** No chatbot downtime do rebuild; revoked source không đọc lại từ cache; GC không xóa cited objects.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T019.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T020 · Trường phái, phương pháp, concept và aliases

- **Mục tiêu:** Trường phái, phương pháp, concept và aliases.
- **Dependencies:** T019.
- **File/module:** `backend/app/knowledge/ontology.py; api/knowledge.py`.
- **Công việc cụ thể:** School/method/topic CRUD, versioned concepts và aliases, author layers; taxonomy seed không bịa definitions; scoped expansion keys.
- **API/schema contract:** 06 concepts;04 ontology;10 schools/terms.
- **Test cần chạy:** `pytest tests/api/test_ontology.py`.
- **Tiêu chí nghiệm thu:** Cùng label dụng ở hai school có 2 identities; change semantic revision không sửa approved cũ.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T020.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T021 · Trích xuất candidates từ nguồn

- **Mục tiêu:** Trích xuất candidates từ nguồn.
- **Dependencies:** T020.
- **File/module:** `backend/app/knowledge/extractor.py; candidate_schemas.py`.
- **Công việc cụ thể:** Structured provider output cho term/assertion/rule/case candidates; source-span validation và external-processing policy; chưa có key vẫn pipeline index được.
- **API/schema contract:** 06 candidates;09 provider privacy.
- **Test cần chạy:** `pytest tests/integration/test_candidates.py with malicious/mock provider`.
- **Tiêu chí nghiệm thu:** All model outputs draft; invalid sources/schema quarantined; không AI approve.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T021.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T022 · Duyệt assertions/rules và relations

- **Mục tiêu:** Duyệt assertions/rules và relations.
- **Dependencies:** T021.
- **File/module:** `backend/app/knowledge/reviews.py; assertions.py`.
- **Công việc cụ thể:** Review transitions, optimistic locks, source/rights checks, audit trail; pending DSL full validation wired sau T031.
- **API/schema contract:** 06 workflow;10 reviews;04 reviews/assertion relations.
- **Test cần chạy:** `pytest tests/api/test_reviews.py`.
- **Tiêu chí nghiệm thu:** Approve/revoke guarded; concurrent reviewer không overwrite; chưa DSL validator thì rule approval blocked rõ.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T022.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T023 · Kho mệnh lệ và structured chart từ sách

- **Mục tiêu:** Kho mệnh lệ và structured chart từ sách.
- **Dependencies:** T022.
- **File/module:** `backend/app/cases; tests/integration/test_cases.py`.
- **Công việc cụ thể:** Table + narrative extraction, ordered 4 pillars, unknown hours, book/user/synthetic origins; case events/source/revision/privacy APIs.
- **API/schema contract:** 06 case contract;10 cases.
- **Test cần chạy:** `pytest tests/integration/test_cases.py tests/api/test_case_access.py`.
- **Tiêu chí nghiệm thu:** Không suy ngược ngày sinh duy nhất; source mapping và owner quyền đúng; ambiguous columns vào review.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T023.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T024 · Ontology releases và dependency impact graph

- **Mục tiêu:** Ontology releases và dependency impact graph.
- **Dependencies:** T023.
- **File/module:** `backend/app/knowledge/releases.py; impact.py; dependencies.py`.
- **Công việc cụ thể:** Snapshot approved concepts/terms/methods, registry dependency edges, stale marking/re-evaluate job contract; filters source_changed review.
- **API/schema contract:** 04 analysis_dependencies;06 impact;10 knowledge/impact.
- **Test cần chạy:** `pytest tests/integration/test_knowledge_impact.py`.
- **Tiêu chí nghiệm thu:** Affected IDs chính xác theo fixture graph; old assertions/cases giữ source; invalid reference rejected.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T024.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T025 · Tập gold retrieval và chuyên môn

- **Mục tiêu:** Tập gold retrieval và chuyên môn.
- **Dependencies:** T024.
- **File/module:** `tests/fixtures/gold; backend/app/evaluation/datasets.py`.
- **Công việc cụ thể:** Tạo dataset/import API, 12 seeds từ audit→≥60 câu có đáp án/spans/grades; chuyên gia review và split theo case/section; nguồn chưa duyệt marked pending.
- **API/schema contract:** 07 benchmark;13 seed gold;10 evaluation-datasets.
- **Test cần chạy:** `pytest tests/integration/test_gold_manifest.py; manual review checklist`.
- **Tiêu chí nghiệm thu:** Locator thật/hash khớp; không clone response hệ thống làm gold; chưa expert sign thì gate blocked.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T025.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T026 · Adapter Calculation Engine và schema facts

- **Mục tiêu:** Adapter Calculation Engine và schema facts.
- **Dependencies:** T008.
- **File/module:** `backend/app/calculation/adapter.py; schemas.py; enums.py`.
- **Công việc cụ thể:** Port legacy functions cần thiết, canonical ASCII typed facts, engine/policy manifest; giữ legacy read-only; không sửa mọi thuật toán trước characterization.
- **API/schema contract:** 08 BirthInput/ChartFacts;02 audit.
- **Test cần chạy:** `pytest tests/unit/test_legacy_adapter.py`.
- **Tiêu chí nghiệm thu:** Golden characterization tái hiện hành vi gốc; tên Việt map ổn; không LLM trong module tính.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T026.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T027 · Timezone và giờ Mặt Trời

- **Mục tiêu:** Timezone và giờ Mặt Trời.
- **Dependencies:** T026.
- **File/module:** `backend/app/calculation/time_normalizer.py; solar_clock.py`.
- **Công việc cụ thể:** Sửa A01/A02/A05: IANA/fold/gap validation, host-independent instants, EOT implementation có reference/tolerance, separation physical/pillar clock.
- **API/schema contract:** 08 time policies;13 CAL01/02/05/06.
- **Test cần chạy:** `pytest tests/unit/test_time_normalization.py tests/unit/test_solar_clock.py`.
- **Tiêu chí nghiệm thu:** Host TZ invariance; EOT seasonal sign/offset đúng reference; unknown zone reject; no double correction.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T027.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T028 · Tiết khí, ngày Tý và chu kỳ vận

- **Mục tiêu:** Tiết khí, ngày Tý và chu kỳ vận.
- **Dependencies:** T027.
- **File/module:** `backend/app/calculation/calendar_adapter.py; luck.py; policy.py`.
- **Công việc cụ thể:** Sửa chuẩn tiết khí UTC, explicit day policies và hour stem; Lưu Niên intervals; Đại Vận methods/direction; validate supported lunar calendar.
- **API/schema contract:** 08 policy/cycles;02 A03/A04/A08/A09.
- **Test cần chạy:** `pytest tests/unit/test_pillars_boundaries.py tests/unit/test_luck.py`.
- **Tiêu chí nghiệm thu:** Lập Xuân UTC+7/+8 same instant consistent; midnight/23 policy rõ; no misleading Gregorian year labels.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T028.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T029 · Oracle độc lập và regression calculation

- **Mục tiêu:** Oracle độc lập và regression calculation.
- **Dependencies:** T028.
- **File/module:** `tests/fixtures/calculation_oracles; tests/integration/test_calculation_oracles.py`.
- **Công việc cụ thể:** Thu thập licensed/official astronomy/tzdata oracle + expert tables; 60/100/120 combinations; Cung Mệnh/Thai Nguyên; distinguish same-library comparisons; boundary uncertainty.
- **API/schema contract:** 13 CAL01–CAL12;08 oracle gate.
- **Test cần chạy:** `pytest tests/integration/test_calculation_oracles.py; specialist signoff`.
- **Tiêu chí nghiệm thu:** Zero unexplained core mismatch; uncertain precise timing flagged; chưa có independent oracle ghi BLOCKED không tự tạo expected.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T029.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T030 · Profiles/charts persistence và API

- **Mục tiêu:** Profiles/charts persistence và API.
- **Dependencies:** T029, T006.
- **File/module:** `backend/app/calculation/service.py; profiles.py; api/charts.py`.
- **Công việc cụ thể:** Encrypted profiles, chart immutable hashes, policy capabilities, unknown-time variants, owned list/delete and dependencies; no automatic private case publish.
- **API/schema contract:** 04 profiles/charts;08 facts;10 charts.
- **Test cần chạy:** `pytest tests/api/test_charts.py tests/integration/test_profile_privacy.py`.
- **Tiêu chí nghiệm thu:** Own-only, reproduce same hash, delete impact đúng, saved chart dùng policy version cũ khi default đổi.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T030.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T031 · DSL validator và typed interpreter

- **Mục tiêu:** DSL validator và typed interpreter.
- **Dependencies:** T024, T030.
- **File/module:** `backend/app/rules/ast.py; types.py; interpreter.py; registry.py`.
- **Công việc cụ thể:** Build allowlist AST, typed fact paths/functions, no dynamic execution, schema/depth/node caps, tri-valued expressions.
- **API/schema contract:** 08 DSL v1.
- **Test cần chạy:** `pytest tests/unit/test_rule_ast.py tests/unit/test_rule_unknown.py`.
- **Tiêu chí nghiệm thu:** Reject eval/import/arbitrary JSONPath; missing hour không kích rule phủ định; deterministic result.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T031.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T032 · Rule DAG, exceptions và conflict trace

- **Mục tiêu:** Rule DAG, exceptions và conflict trace.
- **Dependencies:** T031.
- **File/module:** `backend/app/rules/evaluator.py; trace.py; conflicts.py`.
- **Công việc cụ thể:** Topological evaluation, requires/unless unknown, typed emissions, conflict groups, time scopes, resource caps và trace facts.
- **API/schema contract:** 08 evaluation semantics;04 rule traces.
- **Test cần chạy:** `pytest tests/unit/test_rule_evaluator.py`.
- **Tiêu chí nghiệm thu:** Cycle reject; exception U thành pending; contradictory claims giữ hai sources; stable ordering.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T032.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T033 · Rule approval gates và immutable rulesets

- **Mục tiêu:** Rule approval gates và immutable rulesets.
- **Dependencies:** T032, T022.
- **File/module:** `backend/app/rules/rulesets.py; api/rules.py`.
- **Công việc cụ thể:** Wire full validator vào review; fixtures gắn revision; source/approved/school gates, activate snapshot, synthetic excluded production.
- **API/schema contract:** 06 review;08 rulesets;10 rules/reviews.
- **Test cần chạy:** `pytest tests/integration/test_rulesets.py`.
- **Tiêu chí nghiệm thu:** Draft/revoked/no-source rule không lọt active; same-school/method check; expert approved cases pass.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T033.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T034 · Re-evaluation và stale analysis tracking

- **Mục tiêu:** Re-evaluation và stale analysis tracking.
- **Dependencies:** T033.
- **File/module:** `backend/app/rules/reevaluate.py; knowledge/impact.py`.
- **Công việc cụ thể:** Store dependency snapshots; revision/revoke generate impacted set and new analysis diffs, không rewrite old history; owner scoping.
- **API/schema contract:** 06 impact;10 knowledge/reevaluate.
- **Test cần chạy:** `pytest tests/integration/test_rule_impact.py`.
- **Tiêu chí nghiệm thu:** Expected analysis IDs stale, unrelated IDs không stale; reevaluation preserves both traces.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T034.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T035 · Hybrid candidate retrieval và filters

- **Mục tiêu:** Hybrid candidate retrieval và filters.
- **Dependencies:** T025, T016.
- **File/module:** `backend/app/retrieval/query.py; lexical.py; vector.py; fusion.py`.
- **Công việc cụ thể:** QuerySpec validation, term-scoped expansion, FTS/folded/trgm, cosine candidates, RRF, release+school+ACL+rights filtering, ANN/exact path.
- **API/schema contract:** 07 pipeline 1–5;10 search.
- **Test cần chạy:** `pytest tests/integration/test_retrieval_filters.py; gold Recall run`.
- **Tiêu chí nghiệm thu:** No school/ACL leakage; diacritics query retains nghĩa; measure recall baseline trước tuning.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T035.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T036 · Embedding/reranker benchmark và context packing

- **Mục tiêu:** Embedding/reranker benchmark và context packing.
- **Dependencies:** T035.
- **File/module:** `backend/app/retrieval/reranker.py; context.py; evaluation/ablations.py`.
- **Công việc cụ thể:** Compare profiles trên gold; pin model revisions/license/resources; rerank timeout fallback; merge adjacency/case/exception+budget packing.
- **API/schema contract:** 07 steps 6–7;ADR16–20.
- **Test cần chạy:** `pytest tests/unit/test_context_packing.py; ablation report on gold split`.
- **Tiêu chí nghiệm thu:** Selected profile có report; fallback rõ; không cắt mất exception mà không flag; no mixed vector profiles.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T036.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T037 · Citation resolver và validator

- **Mục tiêu:** Citation resolver và validator.
- **Dependencies:** T036, T017.
- **File/module:** `backend/app/retrieval/citations.py; source_viewer.py`.
- **Công việc cụ thể:** Backend resolves evidence IDs, spans/hash/speaker/source membership, support validation hooks; protected PDF range/highlight endpoints.
- **API/schema contract:** 05 locator;07 citation;10 evidence/source.
- **Test cần chạy:** `pytest tests/integration/test_citations.py`.
- **Tiêu chí nghiệm thu:** ID/page/offset invalid bị chặn; old revision valid vẫn mở; withdrawn source không trả content.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T037.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T038 · LLM adapters, cost reservation và mocks

- **Mục tiêu:** LLM adapters, cost reservation và mocks.
- **Dependencies:** T008, T024.
- **File/module:** `backend/app/reasoning/providers; budgets.py; mocks.py`.
- **Công việc cụ thể:** Typed adapters/capabilities, env-ref secrets, tokenization, retries/timeouts and reservation race; fixture provider tách production; source external processing policy.
- **API/schema contract:** 09 providers;04 usage/budget;10 model-profiles.
- **Test cần chạy:** `pytest tests/integration/test_provider_budget.py`.
- **Tiêu chí nghiệm thu:** Parallel requests không vượt reserved budget; no secret logs; unconfigured provider typed state.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T038.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T039 · Reasoning orchestration cho ba modes

- **Mục tiêu:** Reasoning orchestration cho ba modes.
- **Dependencies:** T034, T037, T038.
- **File/module:** `backend/app/reasoning/orchestrator.py; tools.py; claims.py`.
- **Công việc cụ thể:** Bounded state machine, fact/rule/evidence tools, school-scoped compare, structured claim validation, insufficiency and safety phrasing.
- **API/schema contract:** 09 Answer/tools;08 facts/rules.
- **Test cần chạy:** `pytest tests/integration/test_reasoning_modes.py`.
- **Tiêu chí nghiệm thu:** LLM không sửa facts; unsupported claim/source bị loại; empty corpus/no rule/no model không bịa.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T039.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T040 · Multi-turn conversations và search/delete

- **Mục tiêu:** Multi-turn conversations và search/delete.
- **Dependencies:** T039.
- **File/module:** `backend/app/chat/service.py; memory.py; search.py`.
- **Công việc cụ thể:** Context revision pins chart/school/books; last turns+source-linked summary, owner search/star/rename/delete, idempotent messages.
- **API/schema contract:** 09 memory;10 conversations/messages.
- **Test cần chạy:** `pytest tests/api/test_conversations.py`.
- **Tiêu chí nghiệm thu:** Switch chart không dùng facts cũ; idempotency không duplicate; deleted data không search lại.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T040.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T041 · SSE validated claims và cancellation

- **Mục tiêu:** SSE validated claims và cancellation.
- **Dependencies:** T040, T010.
- **File/module:** `backend/app/chat/stream.py; runs.py; tests/api/test_sse.py`.
- **Công việc cụ thể:** Durable event seq, progress/validated claims, Last-Event-ID replay, terminal fetch, expiry410, cooperative cancel/cost reconcile.
- **API/schema contract:** 09 stream;10 runs/events.
- **Test cần chạy:** `pytest tests/api/test_sse.py with reconnect/kill/cancel`.
- **Tiêu chí nghiệm thu:** Reconnect không gọi model lại; không phát citation chưa validate; owner check mỗi stream.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T041.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T042 · API integration và generated client hoàn chỉnh

- **Mục tiêu:** API integration và generated client hoàn chỉnh.
- **Dependencies:** T041, T030, T023.
- **File/module:** `contracts/openapi.json; frontend/src/lib/api; tests/api/test_full_contract.py`.
- **Công việc cụ thể:** Hoàn thiện toàn route catalog, typed DTO/client, filter/pagination/ETag/idempotency, operation jobs/reference coherence; docs diff check.
- **API/schema contract:** 10 toàn bộ API;04 schema coverage.
- **Test cần chạy:** `pytest tests/api/test_full_contract.py; frontend typecheck; contract diff`.
- **Tiêu chí nghiệm thu:** Mọi route được implement, không placeholder ok; UI contract types sinh từ server.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T042.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T043 · Frontend shell, auth, navigation và empty states

- **Mục tiêu:** Frontend shell, auth, navigation và empty states.
- **Dependencies:** T042.
- **File/module:** `frontend/src/app; components/layout; features/auth`.
- **Công việc cụ thể:** Professional desktop design tokens, login/roles, 13 areas routes, loading/error/no-data components, responsive keyboard/a11y.
- **API/schema contract:** 11 layout/routes;10 auth/dashboard.
- **Test cần chạy:** `Playwright tests/e2e/shell.spec.ts; typecheck`.
- **Tiêu chí nghiệm thu:** 1280/1920 layouts không overflow; unauthorized nav/API đều chặn; không demo counters.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T043.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T044 · Giao diện lập/xem/lưu lá số

- **Mục tiêu:** Giao diện lập/xem/lưu lá số.
- **Dependencies:** T043.
- **File/module:** `frontend/src/features/charts; profiles`.
- **Công việc cụ thể:** Birth form civil/lunar capabilities, zone/fold/unknown time/solar correction; four pillars/cycles/policy/warnings; saved chart actions.
- **API/schema contract:** 11 charts UX;08 input/facts;10 charts.
- **Test cần chạy:** `Playwright tests/e2e/charts.spec.ts`.
- **Tiêu chí nghiệm thu:** Không JS UTC conversion sai; hour unknown hiển thị đúng; backend authoritative, calendar unsupported rõ.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T044.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T045 · Chat UI, nguồn và so sánh

- **Mục tiêu:** Chat UI, nguồn và so sánh.
- **Dependencies:** T044.
- **File/module:** `frontend/src/features/chat; source-drawer; trace-viewer`.
- **Công việc cụ thể:** Three modes/chips/context revisions/history search, SSE reconnect/cancel, claim citations drawer/bbox, rule trace, contrasting sources.
- **API/schema contract:** 11 chat UX;09 streaming;10 chat/evidence.
- **Test cần chạy:** `Playwright tests/e2e/chat.spec.ts`.
- **Tiêu chí nghiệm thu:** Citations mở đúng page, disconnected không duplicate user message; wrong-scope comparison được nêu rõ.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T045.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T046 · Library upload/jobs/OCR review dashboard

- **Mục tiêu:** Library upload/jobs/OCR review dashboard.
- **Dependencies:** T045.
- **File/module:** `frontend/src/features/books; jobs; ocr-review`.
- **Công việc cụ thể:** Batch per-file metadata/rights, progress counters and logs, quality queue, side-by-side page/text/correction impact và retry.
- **API/schema contract:** 11 books/jobs/review;10 upload/correction.
- **Test cần chạy:** `Playwright tests/e2e/ingestion.spec.ts`.
- **Tiêu chí nghiệm thu:** 100-file queue UI không freeze; 412 correction giữ edits; corrupt file retry không restart batch.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T046.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T047 · Knowledge/rules/cases admin UI

- **Mục tiêu:** Knowledge/rules/cases admin UI.
- **Dependencies:** T046.
- **File/module:** `frontend/src/features/knowledge; rules; cases`.
- **Công việc cụ thể:** Concept/scoped aliases, speaker/source edit, approval/revoke with fixtures, ruleset activation, impacted results; case tables/privacy.
- **API/schema contract:** 11 terms/rules/cases;06 workflow;10 knowledge.
- **Test cần chạy:** `Playwright tests/e2e/knowledge.spec.ts`.
- **Tiêu chí nghiệm thu:** Save draft khác approve; cannot execute draft; ambiguous case trụ review; source side-by-side.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T047.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T048 · Evaluation/settings/dashboard UI

- **Mục tiêu:** Evaluation/settings/dashboard UI.
- **Dependencies:** T047.
- **File/module:** `frontend/src/features/evaluation; settings; dashboard`.
- **Công việc cụ thể:** Datasets/runs/failed examples, cost/model configuration, user management, storage/backup status and health; empty no-model guidance.
- **API/schema contract:** 11 eval/settings;10 evaluation/operations.
- **Test cần chạy:** `Playwright tests/e2e/admin.spec.ts`.
- **Tiêu chí nghiệm thu:** Settings không lộ key; báo fixture vs live scores; restore CTA cần preflight+confirmation.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T048.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T049 · Security hardening và privacy deletion

- **Mục tiêu:** Security hardening và privacy deletion.
- **Dependencies:** T048.
- **File/module:** `backend/app/operations/deletion.py; infra/security; tests/security`.
- **Công việc cụ thể:** Run IDOR/CSRF/prompt-injection/upload bombs/secrets scans; implement dependency-aware delete+cache/vector invalidation+ledger, RLS coverage audit.
- **API/schema contract:** 12 security/delete;13 SEC01–07.
- **Test cần chạy:** `pytest tests/security; deletion canary test; dependency scan`.
- **Tiêu chí nghiệm thu:** No critical/high; withdrawn/deleted content không truy xuất qua SSE/cache/source URLs; no secrets in git.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T049.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T050 · Evaluation harness và quality regression

- **Mục tiêu:** Evaluation harness và quality regression.
- **Dependencies:** T049, T025.
- **File/module:** `backend/app/evaluation/runner.py; metrics.py; tests/evaluation`.
- **Công việc cụ thể:** Offline+budgeted live runs, per-item metrics/versions, retrieval/claims/citations/rules/calculation regression; expert review UI/report.
- **API/schema contract:** 07 metrics;13 gates;10 evaluation-runs.
- **Test cần chạy:** `pytest tests/evaluation; run gold held-out suite`.
- **Tiêu chí nghiệm thu:** Gold approved + metrics đạt ngưỡng; judge AI không là sole oracle; reports repeatable.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T050.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T051 · Benchmark throughput, storage và observability

- **Mục tiêu:** Benchmark throughput, storage và observability.
- **Dependencies:** T050.
- **File/module:** `tests/performance; backend/app/operations/metrics.py; reports/benchmarks`.
- **Công việc cụ thể:** 10/100/1000 manifest, 100k/500k pages capacity/load where available, stage throughput/RSS/disk/latency/cost, queues/alerts; chốt resource settings bằng số đo.
- **API/schema contract:** 05 benchmark;12 metrics;13 PERF01–05.
- **Test cần chạy:** `performance runner 3 repeats; EXPLAIN ANALYZE; metrics smoke`.
- **Tiêu chí nghiệm thu:** Không hứa throughput chưa đo; report synthetic vs actual; disk-low pause recover; query quality không giảm ngoài gate.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T051.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T052 · Backup service và CLI

- **Mục tiêu:** Backup service và CLI.
- **Dependencies:** T051.
- **File/module:** `backend/app/operations/backup.py; scripts/backup; tests/integration/test_backup.py`.
- **Công việc cụ thể:** Maintenance lock/drain, pg_dump/blob manifest/checksum/encryption, retention/external destination, scheduler hooks và audit; no secret keys in archive.
- **API/schema contract:** 12 backup;10 operations/backups.
- **Test cần chạy:** `pytest tests/integration/test_backup.py; manual encrypted archive verification`.
- **Tiêu chí nghiệm thu:** Manifest consistent cùng pointers; missing blob làm backup fail; normal down không xóa volumes.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T052.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T053 · Restore drill và disaster recovery

- **Mục tiêu:** Restore drill và disaster recovery.
- **Dependencies:** T052.
- **File/module:** `backend/app/operations/restore.py; scripts/restore; tests/integration/test_restore.py`.
- **Công việc cụ thể:** Preflight/version/key/disk checks, clean-volume restore, FK/source/search/trace checks, deletion ledger replay, worker resume; measure RTO/RPO.
- **API/schema contract:** 12 restore runbook;13 E2E08.
- **Test cần chạy:** `pytest tests/integration/test_restore.py; restore rehearsal report`.
- **Tiêu chí nghiệm thu:** Wrong key/corrupt dump không switch live; intact backup restore được chart/chat/citations và queues.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T053.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T054 · Windows/WSL runbook và update/migration checks

- **Mục tiêu:** Windows/WSL runbook và update/migration checks.
- **Dependencies:** T053.
- **File/module:** `scripts/dev; scripts/dev.ps1; docs/LOCAL_RUNBOOK.md; tests/operations`.
- **Công việc cụ thể:** Validate clean Windows setup/WSL Docker, migrations from prior schema, persisted volumes across update, no destructive default; license/SBOM/dependency locks final.
- **API/schema contract:** 03/12 operations;04 migration.
- **Test cần chạy:** `Run doctor/build/migrate/up on actual Windows WSL2; Linux smoke`.
- **Tiêu chí nghiệm thu:** Ghi environment thực và lệnh; không gọi Linux-only run là Windows tested; blocker minh bạch.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T054.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T055 · Tích hợp hồi phục và test bảo mật cuối

- **Mục tiêu:** Tích hợp hồi phục và test bảo mật cuối.
- **Dependencies:** T054.
- **File/module:** `tests/integration/test_fault_matrix.py; tests/e2e; reports/release`.
- **Công việc cụ thể:** Full integration faults: workers/provider/network/Redis restart, publish during chat, deletion during stream, concurrent review/budget; regression unresolved issue triage.
- **API/schema contract:** 13 integration/security matrix.
- **Test cần chạy:** `scripts/dev test integration; Playwright full; security scan`.
- **Tiêu chí nghiệm thu:** Zero unexplained regression; no data race/citation drift; all core modules use real backend.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T055.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.

### T056 · Nghiệm thu tám kịch bản và bàn giao đầy đủ

- **Mục tiêu:** Nghiệm thu tám kịch bản và bàn giao đầy đủ.
- **Dependencies:** T055.
- **File/module:** `reports/acceptance; README.md; TASKS.md; release manifest`.
- **Công việc cụ thể:** Chạy E2E01–08 có evidence, signed expert gold/calculation review, package source+runbook+locked dependencies+restore report; mark release only if all gates pass.
- **API/schema contract:** 01 requirements;13 release DoD.
- **Test cần chạy:** `scripts/dev test acceptance; verify_release_manifest`.
- **Tiêu chí nghiệm thu:** 8 scenarios pass, no core tasks deferred; nếu gate blocked ghi release candidate, không tuyên bố hoàn thành.
- **Điều kiện hoàn thành:** Tiêu chí trên đạt; tests pass có log, cập nhật contract nếu có thay đổi đã được duyệt; báo cáo `reports/tasks/T056.md`, commit và checkbox. Test chưa chạy hoặc oracle chưa có → BLOCKED, không `[x]`.
