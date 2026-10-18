# 10 · REST API và SSE contract v1

## Quy ước

Base `/api/v1`. JSON UTF-8, snake_case, UUID cho entity IDs, UTC ISO8601 cho timestamps; BirthInput local datetime ngoại lệ được mô tả ở 08. OpenAPI 3.1 generated từ Pydantic là artifact triển khai; so diff với contract này trong CI. Không expose database ORM object tùy ý. Success entity `{data:...,meta:{request_id}}`; list `{data:[],page:{next_cursor:null,has_more:false},meta:{request_id}}`; pagination cursor theo `(created_at,id)`, limit=20 mặc định/max100. Các collection list hỗ trợ q/status/sort được allowlist, không raw SQL.

Lỗi `application/problem+json`: `{type,title,status,code,detail,request_id,field_errors:[{path,message}]}`. Codes: 401 AUTH_REQUIRED; 403 FORBIDDEN; 404 NOT_FOUND (che existence private); 409 CONFLICT/IDEMPOTENCY_MISMATCH; 412 REVISION_MISMATCH; 413 FILE_TOO_LARGE; 415 UNSUPPORTED_TYPE; 422 VALIDATION_ERROR/AMBIGUOUS_LOCAL_TIME/NONEXISTENT_LOCAL_TIME/UNSUPPORTED_CALENDAR; 429 RATE_LIMITED/BUDGET_EXCEEDED; 503 PROVIDER_UNAVAILABLE; 410 SOURCE_WITHDRAWN/EVENTS_EXPIRED. Không trả 200 ok:false cho exception.

Snapshot hợp đồng: `contracts/openapi.json`, sinh bằng `python -m backend.app.cli export-openapi`; test so snapshot với code nên mọi thay đổi route/DTO phải xuất lại và review diff. Mỗi operation có `x-permission` (R/V/A/O/public) và khai báo các problem response. Mutations tạo job/run/version yêu cầu `Idempotency-Key` tối đa 128 ký tự ASCII nhìn thấy được (thiếu/sai → 422). Key scope owner+route, request hash, lưu 24h; cùng key/payload trả cùng result, khác payload 409. PATCH mutable yêu cầu If-Match revision (thiếu → 428 `PRECONDITION_REQUIRED`, lệch → 412 `REVISION_MISMATCH` kèm ETag hiện tại); create response có ETag. `/settings`: GET trả `runtime` (cờ cấu hình đã redact) + settings system và của chính user; PATCH `{scope,key,value}` theo allowlist có kiểu, If-Match `"0"` để tạo; users dùng ETag suy từ `updated_at`. Key idempotency lỗi do request đang chạy → 409 `IDEMPOTENCY_IN_PROGRESS`. Tất cả unsafe cookie requests yêu cầu CSRF token, Origin validation; không dùng CORS `*` với credentials. Upload multipart cũng kiểm CSRF.

Đã triển khai (T042): `backend/app/api/openapi.py` thêm ví dụ vào mọi request body và response JSON khi dựng OpenAPI — success sinh từ schema (UUID/thời gian/enum/pattern hợp lệ), failure là Problem với `status` đúng mã và `code` tiêu biểu của mã đó; không giữ ví dụ viết tay nên không trôi khỏi DTO. `permission(level, idempotent=…, if_match=…)` khai báo header bắt buộc `Idempotency-Key` (1–128 ký tự ASCII nhìn thấy được) và `If-Match` trong `parameters`, nên client sinh ra buộc truyền `params.header`. Contract tests: tên schema không trùng (DTO cùng tên ở hai module được đặt tên riêng: `BirthProfileDTO`/`ModelProfileDTO`, `ChatRunDTO`/`EvaluationRunDTO`, `KnowledgeImpactDTO`/`PageImpactDTO`, `ReleaseActivateInput`/`RulesetActivateInput`, `ReviewResolve*`/`CitationResolve*`, `CitationProblem`…), mọi ví dụ khớp schema của nó, route nào tự đọc `Idempotency-Key`/`If-Match` (theo mã nguồn endpoint) thì khai báo đúng header đó và ngược lại. Frontend: `npm test` kiểm mọi URL `/api/v1` trong mã nguồn — kể cả URL ghép tay cho SSE, upload XHR, ảnh trang — là path có trong contract.

Quyền: R=reader authenticated; V=reviewer; A=admin; O=owner của dữ liệu. `R/O` nghĩa phải là owner hoặc explicit grant có kiểm, không phải reader nào cũng xem. Reviewer kế thừa reader; admin kế thừa reviewer cho kho tri thức. Không suy luận quyền đọc private profiles từ quyền quản trị server.

## Routes xác thực và cấu hình

| Method/path | Quyền | Request | Response / behavior |
|---|---|---|---|
| GET /health/live | public | — | 200 process up, không lộ version/secrets |
| GET /health/ready | A hoặc internal | — | DB/storage/broker status; model unavailable là degraded không chặn chart. Essential fail → 503. Trước T006 chỉ nhận loopback/RFC1918 |
| POST /auth/login | public+rate limit | email,password | 200 user+CSRF, HttpOnly session cookie |
| POST /auth/logout | R | — | 204 revoke current session |
| GET /auth/me | R | — | UserDTO, role, capabilities |
| POST /auth/erasure | O | confirm (email), password, delete_account | ErasureResult counts; xóa cứng dữ liệu riêng (T049) |
| POST /users/{id}/erasure | A | confirm (email người đó), delete_account | ErasureResult counts |
| PUT /messages/{id}/feedback, PUT /analyses/{id}/feedback | O | rating −1/0/1, categories, comment ≤ 1000 | FeedbackDTO; một bản mỗi người/mục, đánh giá lại thì thay; chỉ câu trả lời xong/kết quả có nội dung (409 `NOT_RATEABLE`); MessageDTO/AnalysisDTO kèm `feedback` của chính người gọi |
| GET/POST /users | A | create email,password,role | list/201 UserDTO, không password_hash |
| PATCH /users/{id} | A | role,enabled | 200 ETag; không disable last active admin |
| GET/PATCH /settings | R (own) / A (system) | scope, values allowlist | redacted config; key values không secret |
| GET/POST /model-profiles | R list redacted / A create | ModelProfileInput | 200 list/201 immutable profile |
| POST /model-profiles/{id}/test | A | max_tokens cap | 200 capabilities/latency, usage tracked |
| POST /model-profiles/{id}/activate | A | target kind | 202 operation cho embedding reindex; llm/rerank settings revision mới |
| GET /usage | R own / A aggregate | from,to,profile_id | tokens,cost estimate/actual,budget |

Bootstrap admin chỉ qua local CLI với one-time secret, không public registration endpoint (`python -m backend.app.cli bootstrap-admin`, từ chối khi đã có admin).

Đã triển khai (T038): `GET /model-profiles` (R; kèm `active`, `is_fixture`; config không chứa secret), `POST /model-profiles` (A; kind llm/embedding/reranker, provider theo loại, khóa dạng secret trong config → 422, `secret_ref` ngoài allowlist → 422, trùng → 409; embedding dùng cùng định danh với CLI), `POST /model-profiles/{id}/test` (A; LLM gửi lời nhắn ngắn có tính ngân sách, `check_json` thử JSON; embedding trả số chiều; reranker gọi thử), `POST /model-profiles/{id}/activate` (A; llm/reranker; embedding → 422 vì cần release embed lại toàn bộ), `GET /usage` (R; `from`/`to` theo ngày, `profile_id`; của mình + `all` tổng mọi người cho admin + ngân sách ngày).

Đã triển khai (T006): login trả `{data:{user:UserDTO, csrf_token}}` và cookie `bazi_session` (HttpOnly, SameSite=Strict, Secure ở production, TTL `SESSION_TTL_HOURS` mặc định 12). Mọi request không an toàn có cookie phải gửi header `X-CSRF-Token`; thiếu/sai → 403 `CSRF_FAILED`. Header `Origin` ngoài `ALLOWED_ORIGINS` → 403 `ORIGIN_REJECTED`. Sai email/mật khẩu/tài khoản tắt đều trả cùng 401 `AUTH_REQUIRED`; quá `LOGIN_MAX_FAILURES` lần trong `LOGIN_WINDOW_SECONDS` theo IP hoặc email → 429 `RATE_LIMITED` + `Retry-After` (bộ đếm trong process). Hạ quyền/tắt admin cuối → 409 `LAST_ADMIN`; tắt user thu hồi mọi session của họ. UserDTO: id, email, role, enabled, locale, created_at, updated_at; `/auth/me` thêm capabilities. If-Match/ETag cho PATCH /users thuộc T008.

## Sách, upload, jobs và nguồn

| Method/path | Quyền | Request | Response / behavior |
|---|---|---|---|
| GET/POST /books | R / V | BookInput(title,language,authors[],description) | list/201 BookDTO |
| GET/PATCH /books/{id} | R / V | metadata fields, If-Match | 200; changing school creates review/reclassification impact |
| GET/PATCH /books/{id}/access | V/A | user/role grants, permission | 200; audit và visibility_epoch invalidation |
| POST /ingestion-batches | V | name, pipeline_profile_id, auto_publish bool | 201 batch_id |
| POST /uploads | V | multipart file,batch_id,book_id?,edition_label,rights_status,external_processing_allowed | 201 version_id/object hash/job_id hoặc 200 duplicate_of; server stream/hash |
| GET /books/{id}/versions | R | cursor | VersionDTO[] coverage/status/edition |
| GET /book-versions/{id} | R | — | VersionDTO |
| POST /book-versions/{id}/process | V | pipeline_profile_id?, scope full; Idempotency-Key | 202 JobDTO (generation mới, giữ bản sửa) |
| POST /book-versions/{id}/withdraw | V | reason | 200 đồng bộ: release active mới không có version, visibility_epoch mới |
| DELETE /books/{id} | A | deletion_mode metadata/content, reason | 202 deletion job, dependent impact report |
| GET /ingestion-batches/{id} | V | — | per-file accepted/rejected/counters, không fail all |
| GET /jobs | V | state,batch_id,book_version_id,cursor | JobDTO[] |
| GET /jobs/{id} | V | — | JobDTO + stage checkpoints + typed error |
| GET /jobs/{id}/events | V | after_seq,limit | ordered durable logs |
| POST /jobs/{id}/retry | V | failed_units_only=true | 202 new job parent_id, reusable outputs |
| POST /jobs/{id}/cancel | V | — | 202 cancel_requested hoặc 200 terminal |
| GET /book-versions/{id}/pages | R | cursor | page metadata, quality, printed labels |
| GET /page-revisions/{id} | R | — | PageDTO text/layout/quality, authorized source refs |
| GET /book-versions/{id}/source | R | Range | authorized PDF/DOCX stream, 206 hỗ trợ Range |
| GET /page-revisions/{id}/render | R | scale bounded | image/bản dựng protected, cache private |
| POST /pages/{id}/corrections | V | base_revision_id,changes[],reason; If-Match | 201 new revision + 202 job reference, unchanged source immutable |
| GET /review-items | V | reason,state,book_version_id | review queue |
| POST /review-items/{id}/resolve | V | action accept/exclude/retry/dismiss, reason, base_revision_id; Idempotency-Key | 200 item + job/generation nếu có rebuild |
| GET /generations/{id}/impact | V | — | affected chunks/rules/cases/analyses counters+IDs paginated |
| GET /generations/{id} | V | — | state, manifest, coverage + excluded_ranges, review mở, job, release chứa nó |
| POST /generations/{id}/publish | V | allow_partial,ack_excluded_ranges,activate; Idempotency-Key | 201 release mới (đồng bộ), không rule autoapprove |
| GET /corpus-releases | V | cursor | releases + active pointer (null khi kho rỗng) |
| GET /corpus-releases/{id} | V | — | release + members |
| POST /corpus-releases/{id}/activate | A | expected_active_id | 200 atomic switch; 409 if concurrent |

Đã triển khai (T009): /books (GET R có `q` không dấu + cursor, POST V với authors, GET/PATCH If-Match theo `revision`), /books/{id}/access (GET V, PATCH A thay toàn bộ grants, tăng revision + `visibility_epoch`, ghi audit), /books/{id}/versions, /book-versions/{id}, /ingestion-batches (POST/GET), /uploads. Hiển thị: reviewer/admin thấy toàn kho; reader chỉ thấy sách có grant `read` cho chính họ hoặc role; sách khác trả 404. Sách mới private: người tạo `manage`, role reviewer `review`. Upload bắt buộc `Idempotency-Key`; loại tệp theo magic bytes và phải khớp đuôi (`UNSUPPORTED_TYPE` 415); DOCX bị từ chối khi zip bomb/tên dạng path (`DOCX_INVALID`, `DOCX_EXPANSION_LIMIT`), macro/đối tượng nhúng (`DOCX_ACTIVE_CONTENT`), quan hệ ngoài không phải hyperlink (`DOCX_EXTERNAL_RELATIONSHIP`); quá `MAX_UPLOAD_BYTES` → 413. Cùng bytes (kể cả đồng thời) → 200 `duplicate_of`, không thêm object/version/job. Batch có `pipeline_profile_id` thì mỗi tệp accepted tạo generation building + ingestion job queued + outbox `ingestion.job.queued` trong cùng transaction; không có profile thì job_id null (xử lý sau qua /process). Mỗi tệp, kể cả bị từ chối, có một item trong `GET /ingestion-batches/{id}`.

Đã triển khai (T017): `GET /book-versions/{id}/pages` (R, cursor; revision mới nhất của từng trang + quality), `GET /page-revisions/{id}` (R; text, blocks có offset codepoint, `latest_revision_id`; header `ETag` = id revision mới nhất của trang), `POST /pages/{id}/corrections` (V; bắt buộc `If-Match` = ETag đó và `Idempotency-Key`; body `base_revision_id`, `changes[]` gồm `ordinal` + text/kind/level/role/speaker_layer/table_cells, `reason`; 201 + `ETag` của revision mới, `job_id`, `generation_id`, `coalesced`, `source_changed`; 412 khi trang đã có revision mới hơn, 422 `NO_CHANGE`, 409 `JOB_ACTIVE`/`NOT_PROCESSED`), `GET /generations/{id}/impact` (V; counts luôn có, `kind` = page/chunk_added/chunk_removed/evidence/rule/assertion/case_revision + `cursor` để phân trang ID).

Đã triển khai (T018): publish đồng bộ vì chỉ ghi membership và đổi con trỏ (vector/lexical đã có từ lúc ingest); lỗi gate là 409 với mã `GENERATION_NOT_READY`, `VERSION_WITHDRAWN`, `RIGHTS_RESTRICTED`, `NOTHING_TO_PUBLISH`, `PARTIAL_NOT_ACKNOWLEDGED` (detail liệt kê khoảng trang), `INDEX_INCOMPLETE`, `EMBEDDING_PROFILE_MISMATCH`, `LEXICAL_PROFILE_MISMATCH`, `ONTOLOGY_MISSING`. `activate=false` chỉ dựng release `ready`; admin bật bằng `POST /corpus-releases/{id}/activate` với `expected_active_id` (compare-and-swap: lệch → 409 `ACTIVE_CHANGED`, release không `ready` → 409 `RELEASE_NOT_READY`, gọi lại khi đã active → 200 không đổi gì). Kho rỗng: `GET /corpus-releases` trả 200 `{active: null, releases: []}`.

Đã triển khai (T019): `GET /jobs` (V; lọc state/batch_id/book_version_id, cursor), `GET /jobs/{id}` (JobDTO + `stages[{stage,units,computed,reused,done}]` + `retried_by`), `GET /jobs/{id}/events` (`after_seq`, `limit`; `page.next_cursor` là seq cuối), `POST /jobs/{id}/retry` (202 job con; job chưa kết thúc/thành công → 409 `JOB_NOT_RETRYABLE`, generation đã niêm phong → 409 `GENERATION_CLOSED`, đang có job → 409 `JOB_ACTIVE`; `failed_units_only=false` → 422 vì dựng lại toàn bộ là `/process`), `POST /jobs/{id}/cancel` (202 `cancel_requested` khi worker đang chạy, 200 khi đã kết thúc hoặc hủy xong ngay), `POST /book-versions/{id}/process`, `POST /book-versions/{id}/withdraw`, `GET /review-items` (mặc định `state=open`; lọc reason/book_version_id/generation_id), `POST /review-items/{id}/resolve` (item đã đóng → 409 `REVIEW_CLOSED`; accept/exclude/retry cho item tri thức → 422).

Đã triển khai (T046.1): `GET /page-revisions/{id}/render` (R; `scale` 0,5–3, làm tròn bước 0,25; PNG của trang theo hướng hiển thị, trần 8 triệu pixel; quyền theo sách của phiên bản; ETag theo sha nguồn + trang + scale + renderer, `If-None-Match` → 304, `Cache-Control: private`; DOCX không dựng được → 409 `NO_PAGE_IMAGE`). `GET /pipeline-profiles` (V; mới nhất trước, kèm phiên bản parser/chunker/normalizer/renderer, config và embedding `{model, locality fixture/local/external, ready}`; tạo bằng CLI `pipeline-profile`, chỉ nhận embedding đã provision, phiên bản lấy từ code đang chạy, trùng config hash → trả profile có sẵn). `GET /review-items/{id}` (V) và `scope=page|knowledge` cho `GET /review-items`; ReviewItemDTO thêm `book_title`; JobDTO thêm `book_id`, `book_title`, `edition_label`.

Đã triển khai (T020): `GET/POST /schools` (+ `GET /schools/{id}`), `GET/POST /topics`, `GET/POST /methods` (+ `GET /methods/{id}`, `POST /methods/{id}/revisions` với `base_revision`), `GET/POST /concepts` (list trả revision mới nhất mỗi key, lọc school_id/state/q không dấu, cursor), `GET /concepts/{id}` (terms, các revision, lịch sử review), `POST /concepts/{id}/revisions`, `GET /terms` (q không dấu, school_id, concept_id, state; kèm concept + school), `POST /terms`, `GET /terms/{id}`, school scopes, `POST /reviews` cho method/concept/term/school_scope (assertion/rule/case thêm ở T022). Không có `POST /terms/{id}/revisions`: đổi alias là thêm term mới rồi revoke term cũ.

Đã triển khai (T021): `GET /assertions` (lọc state/school_id/book_version_id/q không dấu, cursor) và `GET /assertions/{id}` (sources với trích dẫn lấy từ revision bất biến, số trang, speaker, relations). Reader chỉ thấy assertion `approved` và trích dẫn từ sách mình được đọc; draft/candidate chỉ reviewer thấy (404 với reader). Ghi/duyệt assertion ở T022.

Đã triển khai (T022): `POST /evidence` (V; `page_revision_id`, `start_offset`, `end_offset` trong một block, `origin`) và `GET /evidence/{id}`; `POST /assertions` (≥ 1 `evidence_ids`), `POST /assertions/{id}/revisions` (`base_revision`, lệch → 412), `POST /assertion-relations`; `GET/POST /rules` (`dsl` sai → 422 `RULE_INVALID` với `field_errors` theo đường dẫn trong tài liệu; trùng `rule_key` → 409), `GET /rules/{id}` (sources, requires, fixtures, reviews; reader chỉ thấy rule approved), `POST /rules/{id}/revisions`, `POST /rules/{id}/validate` (`fixtures[]` thay bộ đang lưu khi rule còn draft; trả lỗi tài liệu, kết quả từng fixture, điều còn chặn duyệt). `POST /reviews` nhận thêm `assertion`, `assertion_relation`, `rule`; gate chặn → 409 `APPROVAL_BLOCKED`.

Đã triển khai (T023): `GET /cases` (lọc school_id/state/origin/book_version_id, cursor), `POST /cases` (`user_case` cho mọi người dùng, riêng tư theo chủ; `book_case`/`synthetic_test` chỉ reviewer, book case cần evidence), `GET /cases/{id}` (revision mới nhất, các revision, nguồn có trích dẫn), `POST /cases/{id}/revisions`, `DELETE /cases/{id}` (204, tombstone; case người khác → 404). Payload sai (trụ ngoài 60 Giáp Tý, có `birth_date`) → 422. `POST /reviews` nhận `case_revision`.

Đã triển khai (T024): các route ontology release và `GET /knowledge/impact` ở bảng trên; `POST /reviews` với `revoke` trả `analyses_stale`. `POST /knowledge/reevaluate` chờ engine luận giải (K6).

Đã triển khai (T036): `POST /search` nhận `rerank` (mặc định bật) và `pack` (trả `bundle` gồm nhóm evidence `E1…`); các route evaluation ở bảng dưới.

Đã triển khai (T037): `POST /search` với `pack` trả `bundle.bundle_id`; `POST /citations/resolve` (R; `bundle_id`, `claims[{text, evidence_ids, quote?}]`) → trạng thái từng claim, lỗi, mức support và citation đã kiểm; 404 bundle không phải của mình, 410 `BUNDLE_EXPIRED`.

Upload 100 sách: frontend tạo batch rồi stream mỗi file với concurrency=2 và key riêng; lỗi 1 file nằm batch item result, không gửi một multipart request 25 GiB. Pause/resume batch client là resume tệp chưa upload; upload một tệp gián đoạn có thể retry toàn tệp và dedupe, không tuyên bố byte-range resumable chưa triển khai. Worker processing resume từ page checkpoint theo 05.

## Tri thức và mệnh lệ

Các list hỗ trợ scope school_id/method_id/topic_id/book_id, q và cursor. API IDs luôn UUID, key như manh_phai được resolve trong ontology/DSL service. Generic resource collection below có schema riêng, không endpoint cho arbitrary table name.

| Method/path | Quyền | Payload / result |
|---|---|---|
| GET/POST /authors | R/V | AuthorInput(name,notes), AuthorDTO |
| GET/POST /schools | R/V | key,label,parent_id,description; SchoolDTO |
| GET/POST /methods | R/V | school_id,key,description; MethodRevisionDTO |
| GET/POST /topics | R/V | key,label,parent_id; TopicDTO |
| GET/POST /concepts | R/V | school_id,canonical_key,label,description; draft revision |
| GET/POST /terms | R/V | concept_id,form_nfc,language,alias_kind,evidence_id; draft |
| POST /concepts/{id}/revisions | V | base_revision, changes, reason | 
| GET/POST /book-versions/{id}/school-scopes | R/V | school_id, first_page?, last_page?, reason → draft scope; duyệt qua /reviews |
| GET/POST /assertions | R/V | AssertionInput theo 06 + evidence_ids |
| GET /assertions/{id} | R | revision + sources + relations |
| POST /assertions/{id}/revisions | V | base_revision,statement,applicability,exceptions,evidence_ids |
| POST /assertion-relations | V | from_id,to_id,relation → draft relation |
| GET/POST /rules | R/V | RuleInput DSL+school/method/sources → draft |
| GET /rules/{id} | R | DSL, sources, tests, lifecycle |
| POST /rules/{id}/revisions | V | base_revision,DSL,evidence_ids,reason |
| POST /rules/{id}/validate | V | fixtures[] | schema/type/DAG/positive-negative-unknown results |
| POST /reviews | V | entity_kind,entity_id,base_revision,decision submit/return/approve/reject/revoke,reason; Idempotency-Key | guarded transition, review row cùng transaction, audit |
| GET/POST /rulesets | R/V | school_id,method_id,rule_revision_ids | snapshot validate + ready, không lấy draft |
| POST /rulesets/{id}/activate | V | expected_current_id | active method setting update atomic |

Đã triển khai (T033/T034): `GET /rulesets` (R; lọc school_id/method_id/state), `POST /rulesets` (V; school_id, method_id, version, `rule_revision_ids?` → 201 state `building` + manifest; 409 `DEPENDENCY_MISSING`/`RULE_CYCLE`/`RULESET_EMPTY`/trùng version), `GET /rulesets/{id}` (members theo thứ tự chạy), `POST /rulesets/{id}/activate` (V; CAS → 409 `ACTIVE_CHANGED`, trả `analyses_stale`); `POST /charts/{id}/analyses` (O; school_id/method_id hoặc ruleset_id, `as_of` YYYY-MM-DD; 202 AnalysisDTO đã completed; 409 `NO_ACTIVE_RULESET`/`RULESET_HAS_REVOKED_RULE`/`RULESET_RETIRED`), `GET /charts/{id}/analyses`, `GET /analyses/{id}`, `GET /analyses/{id}/trace` (cursor), `POST /analyses/{id}/reevaluate` (201 analysis mới + diff). Chưa có: `run_id`/conversation và narrative LLM (T039).
| GET /knowledge/impact | V | entity_kind,entity_id | counts + ID (≤100/kind) phía dưới; analyses/runs chỉ có số đếm |
| GET /ontology-releases, GET /ontology-releases/{id} | R | — | releases, số concept/alias, có được corpus active ghim |
| GET /ontology-releases/preview, POST /ontology-releases | V | version?; Idempotency-Key | diff; 201 release + corpus release ghim nó |
| POST /knowledge/reevaluate | V | dependency_kind,id,analysis_ids? | 202 operation, chỉ analyses được phép |
| GET/POST /cases | R/V hoặc O user case | CaseInput origin,school_id,method_id?,chart_payload(book-case/1),narrative,claimed_events,evidence_ids |
| GET /cases/{id}, POST /cases/{id}/revisions | R / V hoặc O | revision mới từ base_revision (lệch → 412) |
| GET /cases/{id} | R theo visibility | current revision + evidence |
| POST /cases/{id}/revisions | V/O | base_revision,changes,reason |
| DELETE /cases/{id} | V/O | reason | 202 tombstone và impact, rights check |

Có GET detail cho schools/methods/topics/concepts/terms theo `/{id}`. Sửa school/topic metadata dùng PATCH cùng If-Match; thay method/concept nghĩa tạo revision, không PATCH approved content. Candidate jobs dùng review endpoints, không hidden auto-approval route. Rule test fixtures lưu `evaluation_items kind=rule_fixture`, liên kết rule revision trong input/source_manifest.

## Lá số, retrieval, chat

| Method/path | Quyền | Request | Response |
|---|---|---|---|
| GET /calculation-policies | R | — | supported policy + calendar/range capabilities |
| GET/POST /birth-profiles | R/O | label,BirthInput | list/201 redacted ProfileDTO |
| GET/PATCH /birth-profiles/{id} | O | BirthInput,label,If-Match | revision mới, chart cũ unchanged |
| DELETE /birth-profiles/{id} | O | delete_linked_charts bool | 202 operation, impact preview |
| POST /charts | R | birth_input hoặc profile_id+revision; policy_id | 201 ChartFacts, 422 unsupported/ambiguous |
| GET /charts | R/O | q,cursor | owned charts |
| GET /charts/{id} | O | — | ChartFacts pinned |
| DELETE /charts/{id} | O | reason? | 202 operation, related chat redaction/retention policy |
| POST /charts/{id}/analyses | O | school_id,method_id,ruleset_id?,source_scope | 202 run_id,analysis_id |
| GET /analyses/{id} | O | — | Answer+facts refs+trace+stale state |
| GET /analyses/{id}/trace | O | cursor | RuleTrace[] |

Đã triển khai (T030, `backend/app/charts/`, `api/charts.py`): `GET /calculation-policies` (policy + hash + mặc định, lịch `gregorian|lunar_vn|lunar_cn`, phạm vi 1900–2100); `GET/POST /birth-profiles` (danh sách không kèm dữ liệu sinh; tạo kiểm BirthInput bằng engine trước khi lưu, 422 mang code `NONEXISTENT_TIME`/`AMBIGUOUS_TIME`/... và path trường), `GET/PATCH /birth-profiles/{id}` (ETag = revision, PATCH cần If-Match → revision mới), `DELETE /birth-profiles/{id}` (xóa mềm; `delete_linked_charts=true` mới xóa lá số liên kết, trả số đã xóa/giữ); `POST /charts` (`birth_input` hoặc `profile_id` + `profile_revision`, `policy_id` ghi đè; revision cũ → 409 `PROFILE_REVISION_GONE`), `GET /charts` (`q` theo nhãn hồ sơ, cursor), `GET /charts/{id}` (ChartFacts đầy đủ có kiểu, kèm input đã giải mã, `chart_id`, `computed_at`), `DELETE /charts/{id}` (204; có analysis → 409). Mọi bảng theo chủ sở hữu bằng RLS (người khác → 404). Chưa có: xóa qua operation 202 + redaction chat (T05x), analyses (T031–T034/T039).
| POST /search | R | query, mode, top_k, school_ids, book_ids, book_version_ids, topic_ids, page_from/page_to | status ok/no_match/empty_corpus/empty_filters, hits (chunk, ranks, sách, section, trang, spans), expansions, release_id, visibility_epoch, degraded |
| GET /evidence/{id} | R rights | context_blocks<=2 | source locator + excerpt + viewer URL |
| GET/POST /conversations | R/O | title,mode,context | list/201 ConversationDTO |
| GET/PATCH /conversations/{id} | O | title,starred,mode,context,If-Match | 200 revision + context snapshot |
| DELETE /conversations/{id} | O | — | 202 deletion operation |
| GET /conversations/{id}/messages | O | cursor | MessageDTO[] incl claims/citations |
| POST /conversations/{id}/messages | O | content,expected_context_revision,client_message_id | 202 run_id,user_message_id,assistant_message_id,events_url |
| GET /runs/{id} | O | — | state,final_answer?,error,usage |
| GET /runs/{id}/events | O | Last-Event-ID | text/event-stream, events theo 09 |
| POST /runs/{id}/cancel | O | — | 202 or 200 terminal |

Đã triển khai (T040/T041): `GET/POST /conversations` (q tìm tiêu đề + nội dung tin nhắn của mình, `starred`, cursor; context mode/chart/schools/methods/books/as_of được kiểm chủ sở hữu), `GET/PATCH/DELETE /conversations/{id}` (PATCH If-Match revision), `GET /conversations/{id}/messages` (after_seq), `POST /conversations/{id}/messages` (Idempotency-Key; 202 run queued + id hai tin nhắn; 409 `RUN_ACTIVE`, 422 `CHART_REQUIRED`/`SCHOOLS_REQUIRED`), `GET /runs/{id}` (state + answer), `POST /runs/{id}/cancel` (200, idempotent), `GET /runs/{id}/events` (SSE; `Last-Event-ID` hoặc `after_seq`). Sự kiện: run.started, tool.started/completed, retrieval.ready, provider.waiting, answer.claim, answer.completed, run.failed, run.cancelled.
| POST /feedback | O target | message_id hoặc analysis_id,rating,categories,comment | 201 feedback_id |

POST charts analyses tạo conversation nội bộ gắn analysis để dùng cùng run model; DB giữ conversation_id và privacy, UI không cần hiện thread tự động trong chat list (`context.origin=analysis`). Hoặc triển khai service tạo explicit analysis thread và trả conversation_id; contract response luôn có ID này. Research không chart vẫn có source statements; chart mode không source trả facts và limitations.

## Evaluation và operations

| Method/path | Quyền | Request / response |
|---|---|---|
| GET/POST /evaluation-datasets | V | name, version, rights, items[key, kind retrieval/no_answer, input.query+filters, expected.relevant[version,pages,grade]/no_answer, split]; 201 |
| POST /evaluation-datasets/{id}/approve | V | chuyên gia ký: reviewer cho mọi item, dataset approved; đã duyệt → 409 |
| GET /evaluation-datasets/{id}/items | V | paginated expected/verified sources |
| POST /evaluation-runs | V | dataset_id, top_k, rerank, split? → 201 run đồng bộ (≤ 500 item) với metrics + kết quả từng item |
| GET /evaluation-runs/{id} | V | status,metrics,per-item results/report |
| GET /dashboard | R | allowed counters, no private user aggregates |
| GET /operations/metrics | A | queue health, disk, errors, latency, cost |
| POST /operations/backups | A | target configured destination →202 operation_id |
| GET /operations/backups | A | manifest metadata,verified_at |
| POST /operations/restore-preflight | A | backup_id → checklist checksum/schema/keys/disk; không restore ngay |
| POST /operations/restores | A | backup_id,preflight_token,confirmation →202; maintenance mode |
| GET /operations/{id} | authorized requester/A | state,progress,error |
| GET /audit-logs | A | actor/action/target/time,cursor; redacted |

Restore destructive cần confirmation cụ thể trên UI và fresh preflight, không từ tool LLM. Không API đọc `.env` hay tải arbitrary URL. All request bodies `extra=forbid`; payload size caps. Endpoint details/DTOs phải có example success/failure trong OpenAPI ở T008 và contract tests sinh client ở T042.

## DTO dùng chung

BookDTO `{id,title,language,authors:[{id,name,role}],versions_count,active_coverage,revision}`; `active_coverage` (T043.1) = tổng trang `{versions,total,accepted,review_required,excluded}` của các phiên bản sách nằm trong release đang active, null nếu chưa publish. VersionDTO `{id,book_id,edition_label,sha256,size_bytes,status,rights_status,coverage:{total,accepted,excluded,failed},current_generation_id}`. PageDTO `{id,page_id,physical_page_number,page_kind,printed_page_label,text,blocks,quality,render_url}`. JobDTO `{id,state,stage,counters,attempt,retry_at,error:{code,message,retryable}?,generation_id}`. EntityRevisionDTO thêm `{id,key,revision,state,school_id,method_id,evidence_ids,review_history}` theo type. ModelProfileInput chỉ nhận `secret_ref` allowlist đã cấu hình trên server, không env name tùy ý.

SSE example:

```text
id: <run_uuid>:7
event: answer.claim
data: {"claim_id":"c1","text":"...","citations":[{"evidence_id":"<uuid>","physical_page_number":16}],"validated":true}

id: <run_uuid>:8
event: answer.completed
data: {"run_id":"<uuid>","message_id":"<uuid>","status":"supported"}
```

Placeholders minh họa wire format, không là dữ liệu nguồn thật. Final canonical Answer lấy GET runs khi reconnect sau retention.
