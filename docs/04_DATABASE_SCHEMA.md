# 04 · PostgreSQL schema contract

## Quy ước chung

Logical schema v1. Mỗi bảng dưới đây mặc định có `id uuid PRIMARY KEY`, `created_at timestamptz NOT NULL DEFAULT now()`, `updated_at timestamptz NOT NULL DEFAULT now()`, trừ embeddings physical table ghi PK riêng. Cột không có `?` là NOT NULL; dấu `?` là nullable. `FK table` trỏ table.id; `UQ` là UNIQUE; CHECK/constraints ở cột cuối phải được đưa vào migration/test. Junction vẫn có UUID để dễ audit, thêm UNIQUE cặp. Mọi FK có btree index (trừ khi đã là prefix index phù hợp).

Enums lifecycle ở 05/06/09 là contract chuẩn; DDL dùng TEXT+CHECK để migration rõ. JSONB không là chỗ chứa quan hệ tùy tiện: schema versioned, validate Pydantic/JSON Schema trước ghi. FK polymorphic chỉ cho reviews/review_items/analysis_dependencies/audit target: cần registry trigger kiểm tồn tại và delete guard; không gọi đó là FK native. Các quan hệ nghiệp vụ chính dùng FK thật. Tên table đặc biệt `embeddings_<collection>` là pattern vật lý, không tên SQL literal. `rulesets` active pointer nằm settings theo method; không suy active bằng revision số lớn nhất. `book_versions` visibility là private-by-default, book_access seed cho uploader và reviewer quản trị theo policy.

Triển khai: Alembic tại `backend/migrations` (SQL viết tay, file này là contract). M001–M003 có từ T004, M004–M007 từ T005, M008 (role `bazi_runtime`, RLS, last-admin guard) từ T006. Enum đã chốt (TEXT+CHECK):

- `objects.state` staging/ready/quarantined/deleting; `storage_backend` local/s3. `book_versions.status` active/withdrawn (withdrawn ⇔ `withdrawn_at`). `book_access.role_scope` reader/reviewer/admin, `permission` read/review/manage. `settings.scope` system/user (user ⇔ `owner_id`).
- `pages.page_kind` pdf_page/docx_rendered_page/docx_anchor. `page_revisions.state`, `chunks.quality_state` accepted/review_required/excluded. `blocks.kind` paragraph/heading/table/figure/caption. `chunks.kind` text/table/case. `speaker_layer` original_author/commentator/translator/editor/unknown (06).
- `generations.state` building→ready→published→superseded, mọi trạng thái → withdrawn. `corpus_releases.state` building→ready→active→retired (ready/building → retired). `embedding_collections.distance` cosine/l2/inner_product, `state` provisioning/ready/retired.

- Vòng đời duyệt (methods, concepts, terms, assertions, assertion_relations, knowledge_rules, case_revisions): draft → in_review → approved | rejected, in_review → draft, approved → revoked. Bản ghi mới bắt buộc `draft`; chuyển sang approved/rejected/revoked cần một `reviews` cùng decision trong **cùng transaction**; cột nội dung đóng băng ngoài draft (sửa = revision mới). Rule approved cần ≥1 `rule_sources`; sources/dependencies chỉ sửa khi rule còn draft; dependency không được tạo vòng.
- Snapshot (`ontology_releases`, `rulesets`): building → published → retired. `calculation_policies` draft → active → retired, config bất biến sau active. `chat_runs.state` theo 09; `ingestion_jobs.state` theo 05; `chart_analyses.status` pending/completed/failed/stale/withdrawn, answer bất biến sau completed.
- Tham chiếu đa hình (`reviews`, `review_items`, `analysis_dependencies`) đi qua bảng nội bộ `entity_registry(kind, table_name)`: kind lạ hoặc target không tồn tại bị từ chối; target đang bị tham chiếu không xóa được. `audit_logs.target_kind` không ràng buộc vì audit sống lâu hơn entity.
- `ingestion_jobs` có thêm `pipeline_profile_id` (FK nhiều cột về generation) để unique partial index "một active job/version/profile" không phụ thuộc trigger. `reviews` append-only; `audit_logs` chỉ xóa bởi retention job (`SET LOCAL bazi.retention = 'on'`).
- Seed (M004, idempotent, `SET LOCAL bazi.seed = 'on'`): schools `tu_tru` (gốc) → `manh_phai`, `tu_binh`; 27 concept cấu trúc của `tu_tru` (10 Can, 12 Chi, 5 Ngũ Hành) với term Việt + chữ Hán; 5 topics; ontology release `seed-1` published. Không seed assertion, rule, case hay evidence.

Hash dùng domain `sha256_hex` (64 hex thường). `page_revisions.text_hash` = SHA256 UTF-8 của `normalized_text`, `chunks.content_hash` = SHA256 của `text`, cả hai là CHECK. `manifest_hash` của generation/release chỉ được NULL khi `building` (hoặc withdrawn/retired) và đóng băng sau đó. `bbox` là mảng 4 số 0..1 với x0≤x1, y0≤y1, hoặc JSON `null` cho nguồn không có hình học (DOCX).

Extension: pgvector, pg_trgm, unaccent, citext. Không làm generated column gọi unaccent không immutable mà bỏ qua lỗi; cập nhật folded text/tsvector qua ingestion application hoặc trigger versioned. Không đổi dictionary âm thầm trên dữ liệu cũ.

## Data dictionary

### `users`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| email citext UQ; password_hash text; role text CHECK admin/reviewer/reader; enabled bool; locale text | soft-delete disable; owner dữ liệu không cascade tự động |

### `sessions`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| user_id uuid FK users; token_hash text UQ; csrf_hash text; expires_at timestamptz; revoked_at timestamptz? | index user_id, expires_at; chỉ hash token |

### `settings`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| scope text; owner_id uuid? FK users; key text; value jsonb; revision int | UQ NULLS NOT DISTINCT(scope,owner_id,key); optimistic lock |

### `model_profiles`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| kind text CHECK llm/embedding/reranker; provider text; model_name text; model_revision text; dimension int?; config jsonb; secret_ref text?; profile_hash char(64) UQ; enabled bool | immutable config; không lưu secret bytes |

### `objects`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| sha256 char(64) UQ; storage_backend text; object_key text UQ; size_bytes bigint CHECK >=0; detected_mime text; state text; encrypted bool | state staging/ready/quarantined/deleting; object metadata không tự cấp quyền |

### `authors`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| name text; normalized_name text; notes text? | index normalized_name; không bắt name unique vì trùng người |

### `books`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| title text; normalized_title text; language text; description text?; revision int; created_by uuid FK users; deleted_at timestamptz? | GIN/trgm title; không UQ title |

### `book_authors`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| book_id uuid FK books; author_id uuid FK authors; role text; ordinal int | UQ(book_id,author_id,role); role author/commentator/translator/editor |

### `book_versions`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| book_id uuid FK books; object_id uuid FK objects; edition_label text; version_no int; rights_status text; external_processing_allowed bool; status text; uploaded_by uuid FK users; withdrawn_at timestamptz? | UQ(book_id,version_no); UQ(book_id,object_id); metadata rights không suy từ tên sách |

### `book_access`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| book_id uuid FK books; user_id uuid? FK users; role_scope text?; permission text | CHECK đúng một user_id/role_scope; UQ NULLS NOT DISTINCT(book_id,user_id,role_scope,permission) |

### `pipeline_profiles`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| name text; parser_version text; chunker_version text; normalizer_version text; renderer_version text?; embedding_profile_id uuid FK model_profiles; config jsonb; config_hash char(64) UQ | immutable, version của OCR và thuật ngữ trong config |

### `generations`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| book_version_id uuid FK book_versions; pipeline_profile_id uuid FK pipeline_profiles; base_generation_id uuid? FK generations; state text; manifest_hash char(64)?; coverage jsonb | index(book_version_id,state); chỉ ready được release |

### `pages`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| book_version_id uuid FK book_versions; physical_page_number int; page_kind text; source_anchor jsonb? | UQ(book_version_id,physical_page_number,page_kind); PDF n>=1; DOCX anchor sequence nội bộ không giả trang in |

### `page_revisions`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| page_id uuid FK pages; revision_no int; base_revision_id uuid? FK page_revisions; raw_text text; normalized_text text; offset_map jsonb; layout jsonb; printed_page_label text?; printed_label_verified bool; text_hash char(64); quality jsonb; state text; rendered_object_id uuid? FK objects | UQ(page_id,revision_no); content immutable; layout gồm dimension/rotation/bbox |

### `generation_pages`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| generation_id uuid FK generations; page_revision_id uuid FK page_revisions; page_id uuid FK pages | UQ(generation_id,page_id); revision phải thuộc page_id và version generation |

### `blocks`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| page_revision_id uuid FK page_revisions; ordinal int; kind text; bbox jsonb; start_offset int; end_offset int; text text; table_cells jsonb?; speaker_layer text; attributes jsonb | UQ(page_revision_id,ordinal); offsets hợp lệ; kind paragraph/heading/table/figure/caption |

### `sections`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| generation_id uuid FK generations; parent_id uuid? FK sections; title text; path text; ordinal int; speaker_layer text; school_id uuid? FK schools | UQ(generation_id,path); parent cùng generation, DAG |

### `chunks`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| content_hash char(64); text text; token_count int; language text; kind text; speaker_layer text; quality_state text | immutable; không UQ content_hash toàn cục vì provenance khác nhau |

### `chunk_spans`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| chunk_id uuid FK chunks; page_revision_id uuid FK page_revisions; block_id uuid FK blocks; ordinal int; start_offset int; end_offset int; bbox jsonb; chunk_start int; chunk_end int | UQ(chunk_id,ordinal); offset range CHECK; block thuộc revision |

### `generation_chunks`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| generation_id uuid FK generations; chunk_id uuid FK chunks; section_id uuid FK sections; ordinal int | UQ(generation_id,ordinal); UQ(generation_id,chunk_id); source thuộc version của generation |

### `search_entries`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| chunk_id uuid FK chunks; lexical_profile_version text; text_nfc text; text_folded text; ts_nfc tsvector; ts_folded tsvector | UQ(chunk_id,lexical_profile_version); GIN hai tsvector + trgm text_folded |

### `embedding_collections`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| profile_id uuid FK model_profiles; dimension int; distance text; physical_table text UQ; state text | UQ(profile_id); table name generated/allowlist, không client SQL |

### `embeddings_<collection>`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| chunk_id uuid FK chunks; content_hash char(64); vector vector(D); embedding_hash char(64) | PK chunk_id thay id mặc định; D cố định mỗi collection; HNSW vector_cosine_ops; code quản lý qua registry |

### `corpus_releases`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| parent_id uuid? FK corpus_releases; embedding_collection_id uuid FK embedding_collections; ontology_release_id uuid FK ontology_releases (FK thêm ở T005); lexical_profile_version text; state text; manifest_hash char(64)? | index state; immutable memberships sau READY |

### `corpus_members`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| release_id uuid FK corpus_releases; book_version_id uuid FK book_versions; generation_id uuid FK generations | UQ(release_id,book_version_id); generation cùng book_version |

### `active_corpus`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| slot text UQ; release_id uuid FK corpus_releases; visibility_epoch bigint | slot default; singleton id; compare-and-swap pointer transaction; không có row trước first publish → empty corpus |

### `schools`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| key text UQ; label text; parent_id uuid? FK schools; description text | no parent cycles |

### `methods`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| school_id uuid FK schools; key text; revision int; description text; state text | UQ(school_id,key,revision); approved immutable |

### `topics`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| key text UQ; label text; parent_id uuid? FK topics | no cycles |

### `concepts`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| school_id uuid FK schools; canonical_key text; label text; description text; revision int; state text | UQ(school_id,canonical_key,revision) |

### `terms`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| concept_id uuid FK concepts; form_nfc text; form_folded text; language text; alias_kind text; state text; evidence_id uuid? FK evidence_spans | UQ(concept_id,form_nfc,language,alias_kind); GIN trgm form_folded; alias thuộc concept revision |

### `ontology_releases`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| version text UQ; state text; manifest_hash char(64) | immutable snapshot |

### `ontology_members`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| release_id uuid FK ontology_releases; concept_id uuid FK concepts; term_id uuid? FK terms; method_id uuid? FK methods | UQ NULLS NOT DISTINCT(release_id,concept_id,term_id,method_id); terms/method consistent school |

### `chunk_classifications`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| chunk_id uuid FK chunks; generation_id uuid FK generations; school_id uuid? FK schools; topic_id uuid? FK topics; concept_id uuid? FK concepts; status text; confidence numeric?; classification_version text | CHECK ít nhất một classification; AI proposed khác reviewed; immutable khi generation publish; chỉ phân loại matching generation được query |

### `evidence_spans`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| book_version_id uuid FK book_versions; page_revision_id uuid FK page_revisions; block_id uuid FK blocks; start_offset int; end_offset int; bbox jsonb; quote_hash char(64); speaker_layer text; origin text | CHECK offsets; composite consistency source/page/block; excerpt lấy từ revision, không rewrite |

### `assertions`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| assertion_key text; revision int; school_id uuid FK schools; method_id uuid? FK methods; concept_id uuid? FK concepts; statement text; applicability jsonb; exception_text text?; origin text; state text; author_id uuid FK users | UQ(assertion_key,revision); approved immutable |

### `assertion_sources`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| assertion_id uuid FK assertions; evidence_id uuid FK evidence_spans; relation text | UQ(assertion_id,evidence_id,relation) |

### `assertion_relations`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| from_id uuid FK assertions; to_id uuid FK assertions; relation text; state text | UQ(from_id,to_id,relation); no self link |

### `knowledge_rules`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| rule_key text; revision int; school_id uuid FK schools; method_id uuid FK methods; assertion_id uuid? FK assertions; dsl jsonb; dsl_hash char(64); fact_schema_version text; state text; author_id uuid FK users | UQ(rule_key,revision); approved không UPDATE nội dung |

### `rule_sources`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| rule_id uuid FK knowledge_rules; evidence_id uuid FK evidence_spans | UQ(rule_id,evidence_id); approved rule phải ≥1 source hợp lệ trừ structural engine rule riêng |

### `rule_dependencies`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| rule_id uuid FK knowledge_rules; requires_id uuid FK knowledge_rules | UQ(rule_id,requires_id); no self; DAG kiểm trong build |

### `rulesets`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| school_id uuid FK schools; method_id uuid FK methods; version text; state text; manifest_hash char(64) | UQ(school_id,method_id,version) |

### `ruleset_members`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| ruleset_id uuid FK rulesets; rule_id uuid FK knowledge_rules; ordinal int | UQ(ruleset_id,rule_id); UQ(ruleset_id,ordinal); same school/method |

### `reviews`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| entity_kind text; entity_id uuid; reviewer_id uuid FK users; decision text; reason text; base_revision int | polymorphic reference kiểm trigger registry; append-only; decision approve/reject/revoke |

### `review_items`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| generation_id uuid? FK generations; page_revision_id uuid? FK page_revisions; entity_kind text?; entity_id uuid?; reason_code text; severity text; state text; assigned_to uuid? FK users; resolution jsonb? | index(state,severity,created_at); ít nhất một target; polymorphic guard |

### `cases`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| case_key text UQ; owner_id uuid? FK users; origin text; visibility text; deleted_at timestamptz? | user case owner bắt buộc; book case không mặc định public Internet |

### `case_revisions`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| case_id uuid FK cases; revision int; school_id uuid FK schools; method_id uuid? FK methods; chart_payload jsonb; narrative text; claimed_events jsonb; state text; quality jsonb | UQ(case_id,revision); no fabricated birth date |

### `case_sources`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| case_revision_id uuid FK case_revisions; evidence_id uuid FK evidence_spans | UQ(case_revision_id,evidence_id) |

### `birth_profiles`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| owner_id uuid FK users; label text; birth_input_encrypted bytea; crypto_key_version text; revision int; deleted_at timestamptz? | index owner_id; serialize BirthInput chuẩn trước encrypt |

### `calculation_policies`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| key text; revision int; config jsonb; manifest_hash char(64); state text | UQ(key,revision); immutable sau active |

### `bazi_charts`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| owner_id uuid FK users; profile_id uuid? FK birth_profiles; profile_revision int?; policy_id uuid FK calculation_policies; input_snapshot_encrypted bytea; facts jsonb; facts_hash char(64); engine_manifest jsonb; validation_status text | index(owner_id,created_at); fact JSON validate chart-facts/1; sensitive timestamps trong facts được bảo vệ quyền và disk encryption |

### `chart_analyses`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| owner_id uuid FK users; chart_id uuid FK bazi_charts; ruleset_id uuid? FK rulesets; corpus_release_id uuid? FK corpus_releases; answer jsonb; status text; stale_reason text?; run_id uuid? FK chat_runs | index(chart_id,created_at); immutable completed answer |

### `rule_traces`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| analysis_id uuid FK chart_analyses; rule_id uuid FK knowledge_rules; status text; predicates jsonb; emissions jsonb; conflicts jsonb | UQ(analysis_id,rule_id); trace facts có cùng owner analysis |

### `conversations`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| owner_id uuid FK users; title text; starred bool; context jsonb; revision int; deleted_at timestamptz? | index(owner_id,updated_at); context IDs validate quyền |

### `messages`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| conversation_id uuid FK conversations; seq bigint; role text; content text; structured_answer jsonb?; status text; run_id uuid? FK chat_runs | UQ(conversation_id,seq); GIN content search có owner join |

### `chat_runs`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| conversation_id uuid FK conversations; user_message_id uuid FK messages; assistant_message_id uuid FK messages; owner_id uuid FK users; mode text; context_snapshot jsonb; model_profile_id uuid? FK model_profiles; corpus_release_id uuid? FK corpus_releases; state text; error jsonb?; prompt_version text | FK vòng tạo deferred; index(state,updated_at); user/assistant thuộc conversation |

### `run_events`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| run_id uuid FK chat_runs; seq bigint; event_type text; payload jsonb; expires_at timestamptz | UQ(run_id,seq); index expires_at, replay owner guard |

### `claims`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| message_id uuid? FK messages; analysis_id uuid? FK chart_analyses; local_key text; text text; kind text; school_id uuid? FK schools; support_status text; inference_level text; fact_paths jsonb; trace_refs jsonb | CHECK ít nhất một message/analysis; local_key unique theo nonnull parent |

### `citations`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| claim_id uuid FK claims; evidence_id uuid FK evidence_spans; chunk_id uuid? FK chunks; corpus_release_id uuid FK corpus_releases; validation jsonb; display_snapshot jsonb | UQ(claim_id,evidence_id); source membership coherent |

### `analysis_dependencies`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| analysis_id uuid? FK chart_analyses; run_id uuid? FK chat_runs; dependency_kind text; dependency_id uuid; content_hash char(64)? | CHECK có parent; index(dependency_kind,dependency_id); registry triggers giữ referential integrity |

### `ingestion_batches`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| created_by uuid FK users; name text; state text; config jsonb | index(created_by,created_at) |

### `ingestion_jobs`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| batch_id uuid? FK ingestion_batches; book_version_id uuid FK book_versions; generation_id uuid FK generations; pipeline_profile_id uuid FK pipeline_profiles; parent_job_id uuid? FK ingestion_jobs; requested_by uuid FK users; state text; counters jsonb; error jsonb?; cancel_requested bool | index(state,updated_at); chỉ một active job/version/profile qua partial unique index |

### `job_stages`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| job_id uuid FK ingestion_jobs; stage text; unit_key text; input_hash char(64); idempotency_key char(64) UQ; state text; attempt int; checkpoint jsonb; output_ref jsonb; lease_until timestamptz?; fencing_token bigint; worker_id text? | index(state,lease_until); unit_key page/chunk/batch |

### `job_events`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| job_id uuid FK ingestion_jobs; seq bigint; level text; code text; payload jsonb | UQ(job_id,seq); không log raw sensitive text |

### `outbox_events`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| event_id uuid UQ; topic text; payload jsonb; published_at timestamptz?; attempts int | index unpublished partial; ghi cùng transaction nghiệp vụ |

### `processed_events`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| consumer text; event_id uuid; processed_at timestamptz | UQ(consumer,event_id) |

### `idempotency_keys`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| owner_id uuid FK users; route text; key text; request_hash char(64); status text; response_code int?; response jsonb?; expires_at timestamptz | UQ(owner_id,route,key); key same payload replay, khác payload 409 |

### `evaluation_datasets`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| name text; version text; split_manifest jsonb; rights jsonb; state text | UQ(name,version) |

### `evaluation_items`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| dataset_id uuid FK evaluation_datasets; key text; kind text; input jsonb; expected jsonb; source_manifest jsonb; reviewer_id uuid? FK users; split text | UQ(dataset_id,key); gold review bắt buộc release |

### `evaluation_runs`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| dataset_id uuid FK evaluation_datasets; requested_by uuid FK users; config_snapshot jsonb; status text; metrics jsonb; report_object_id uuid? FK objects | index(status,created_at) |

### `evaluation_results`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| run_id uuid FK evaluation_runs; item_id uuid FK evaluation_items; actual jsonb; scores jsonb; status text; duration_ms int | UQ(run_id,item_id) |

### `feedback`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| user_id uuid FK users; message_id uuid? FK messages; analysis_id uuid? FK chart_analyses; rating int; categories jsonb; comment text? | CHECK rating -1..1; có target và quyền own |

### `usage_records`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| owner_id uuid FK users; run_id uuid? FK chat_runs; job_id uuid? FK ingestion_jobs; profile_id uuid FK model_profiles; provider_request_id text?; input_tokens bigint; output_tokens bigint; estimated_cost numeric(18,8); actual_cost numeric(18,8)?; currency text; status text | index(owner_id,created_at); estimate khác actual |

### `budget_reservations`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| owner_id uuid FK users; usage_id uuid FK usage_records; reserved_cost numeric(18,8); expires_at timestamptz; status text | row/advisory lock budget kỳ; release reservation không làm mất actual usage |

### `operation_jobs`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| kind text; requested_by uuid FK users; state text; progress jsonb; error jsonb?; target_manifest jsonb; idempotency_key char(64) UQ; lease_until timestamptz?; fencing_token bigint; checkpoint jsonb; cancel_requested bool | kind deletion/backup/restore/reindex/reevaluate; same durable lease runner |

### `backups`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| operation_job_id uuid FK operation_jobs; manifest_object_id uuid FK objects; archive_location text; db_schema_version text; checksum char(64); encryption_key_ref text; state text; verified_at timestamptz? | không lưu recovery key trong backup; manifest truy cập admin |

### `audit_logs`

| Cột bổ sung (ngoài các cột chung) | Ràng buộc / index / ghi chú |
|---|---|
| actor_id uuid? FK users; action text; target_kind text; target_id uuid?; trace_id text; redacted_diff jsonb; outcome text | append-only; index(target_kind,target_id,created_at); không raw birth/key/chat |


## Quan hệ, invariants và index chuyên biệt

`book → book_version → page → page_revision → block`; generation chọn revision qua generation_pages, chọn chunk qua generation_chunks. `chunk_spans` nối chunk về revision/block; `evidence_spans` là locator độc lập chunk để re-chunk không làm gãy sources. `corpus_release → corpus_members → generation` là membership immutable. Search query chỉ chunks qua membership này.

Composite integrity triển khai bằng UNIQUE phụ và FK nhiều cột khi có thể: `(id,page_id)` page_revisions; `(id,page_revision_id)` blocks; `(id,book_version_id)` pages/generations; `(id,generation_id)` sections. Triggers kiểm source page thuộc version của generation/evidence, chunk spans thuộc generation version, start/end không vượt text, speaker không bị đổi giữa spans. Đã triển khai ở M003: block offsets ≤ độ dài `normalized_text`; span nằm trong block và trong độ dài chunk text, cùng speaker với chunk; chunk chỉ vào generation khi có ≥1 span và mọi span trỏ đúng page revision mà generation chọn qua `generation_pages`; membership của generation/release chỉ đổi khi còn `building`; `active_corpus` chỉ trỏ release `active`, `visibility_epoch` không giảm. Bảng nội dung (pages, page_revisions nội dung, blocks, sections, chunks, chunk_spans, memberships) chỉ insert; cột bất biến bị trigger chặn UPDATE. Service test không thay DB integrity test; concurrent bypass cũng phải bị chặn.

`chat_runs` ↔ messages và analyses ↔ chat_runs có vòng FK: tạo tables trước rồi ALTER FK DEFERRABLE INITIALLY DEFERRED trong migration, create pending IDs trong một transaction. `school_id` trong sections có FK được thêm sau schools. Physical embedding table tên server-generated, vector(D) fixed theo profile, ANN index chỉ tạo khi benchmark đủ lớn. Registry+Alembic quản lý provisioning collection, không cho admin nhập arbitrary table name. Cùng chunk reused có vector một lần mỗi profile; content hash guard chống stale vector.

Index cần thêm: GIN chunks text search ở search_entries; HNSW mỗi collection; btree corpus_members(release_id,generation_id), generation_chunks(generation_id,chunk_id), chunk_spans(page_revision_id), evidence_spans(book_version_id,page_revision_id), rule_sources(evidence_id), case_sources(evidence_id); GIN chart facts chỉ thêm khi có query thật, không index mọi JSONB. Partial index jobs WHERE state in active states, review queue open, outbox published_at IS NULL. `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu scale để xác nhận plan.

## Concurrent update và publish

Mutable resources có revision/ETag (`settings`, `books`, `conversations`). API If-Match mất race →412. Nội dung immutable table chỉ insert revision; review state có thể transition bằng guarded transaction và log. Active corpus pointer dùng row lock; chỉ release READY, collection profile và ontology coherent được set ACTIVE, previous chuyển RETIRED. Một slot chỉ có một pointer; không dựa vào nhiều rows ACTIVE không kiểm soát.

## Xóa, retention, quyền

DB runtime không là superuser/migration role. Đã triển khai (M008): role NOLOGIN `bazi_runtime` (NOSUPERUSER, NOBYPASSRLS) có quyền DML trên bảng nghiệp vụ, không ghi được `alembic_version`/`entity_registry`; login của API là thành viên role này và không sở hữu bảng. RLS trên birth_profiles, bazi_charts, chart_analyses, rule_traces, conversations, messages, chat_runs, run_events, claims, citations, analysis_dependencies, feedback, usage_records, budget_reservations, idempotency_keys và settings (scope user); `app.user_id` trống → không thấy dòng nào. Hàm chặn xóa tham chiếu chạy SECURITY DEFINER để thấy mọi owner. Trigger giữ ít nhất một admin enabled (advisory lock). RLS cho user-owned profiles/charts/conversations/messages/runs/analyses/feedback và checks xuyên owner joins; `SET LOCAL app.user_id` mỗi transaction từ principal đã xác thực, không tin header user_id. Runtime DB role NO BYPASSRLS; migration role riêng. Kho tri thức theo book_access và reviewer/admin role. Admin nghiệp vụ được quản trị kho, không tự động nhận quyền đọc mọi hồ sơ sinh riêng nếu không có grant/user export; operational DBA vẫn có khả năng đọc DB, cần encryption/OS protection.

Default ON DELETE RESTRICT cho nguồn/version/evidence/rule/corpus để không phá citation. Hard-delete job trước hết withdraw, cancel runs, loại active memberships và embeddings, redacts/deletes dependent citation excerpts, rồi xóa nội dung theo dependency order; giữ tombstone tối thiểu. Chat/profile deletion cascade private objects theo explicit deletion transaction; không cascade từ user đến toàn bộ sách đã nhập. Shared objects chỉ xóa khi không còn references, kiểm job trong transaction+lock. Backup retention có thể giữ dữ liệu đã xóa tới 30 ngày, phải công khai trong UI và deletion ledger được áp lại sau restore.

## Migrations

M001 users/auth/settings/model profiles; M002 objects/books/access; M003 pages/generations/chunks/search; M004 knowledge/evidence/reviews/cases; M005 charts/rulesets; M006 chat/claims/citations/dependencies; M007 jobs/outbox/evaluation/operations; M008 RLS/indexes/composite constraints. Đây là logical grouping; Alembic revisions phải có DAG tuyến tính và references deferred hợp lệ. `alembic upgrade head` empty DB và upgrade từ previous release đều test. Seed ontology trong migration data step idempotent, không gọi API/model trong migration.

Index lớn dùng CREATE INDEX CONCURRENTLY ngoài transaction migration phù hợp; schema expand→backfill→switch→contract, không drop cột đang dùng. Downgrade chỉ support nếu lossless; restore backup là rollback cho destructive migration và cần approval. T053 chứng minh restore source blobs+DB+encryption references và rebuild indexes theo version.
