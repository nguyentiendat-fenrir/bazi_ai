# 12 · Bảo mật, vận hành và khôi phục

## Triển khai: Windows dev → Git → Ubuntu 22.04

Theo [ADR-21](15_ARCHITECTURE_DECISIONS.md#adr-21-chi-tiết): Windows native chạy code
và unit tests bằng Python 3.12 qua uv, không bắt buộc WSL/Docker. Ubuntu 22.04 là
runtime đích: Docker Engine + Compose, repo trên filesystem Linux, cùng host với
Gemma. Runbook từng bước ở [README](../README.md). Sách, `.env`, models, text/index,
DB và checkpoints nằm ngoài Git; chuyển sách riêng và đối chiếu SHA256. Giữ tên
project/volume; không `down -v` khi update.

Compose có `postgres` (pgvector), `redis`, `corpus-inspect` chạy một lần, và profile `app` gồm `worker` (mọi stage kể cả OCR, image `app` có Tesseract 5.3) và `watchdog` (dispatcher + reconciler): chỉ mạng internal (không Internet), root read-only, `/tmp` tmpfs, non-root 10001, drop capabilities, no-new-privileges, giới hạn PIDs/RAM/CPU; dùng login `POSTGRES_APP_USER`.
Đích dài hạn: gateway, frontend (khi có UI thật), api, worker-ingest, worker-ocr,
worker-ai, dispatcher/watchdog; mọi worker dùng cùng backend image với command khác.
Service chỉ được thêm cùng implementation và tests. Profiles cho OCR/model local/S3
test là optional. Volumes: pgdata, objects, model_cache, staging; backup mã hóa ở
đường dẫn ngoài các volumes này. Redis state không là nguồn duy nhất cần restore.

Runbook từng bước (T054) ở README · Ubuntu 22.04: `scripts/dev migrate --status`; `scripts/dev migrate --backup-dest <dir>` từ chối khi không có backup < 24 giờ (`--without-backup` chỉ cho DB trống); `scripts/dev bootstrap --email …` (mật khẩu admin từ `BAZI_BOOTSTRAP_PASSWORD` hoặc nhập, không trên dòng lệnh); `doctor --target deploy` coi `POSTGRES_PASSWORD`, `POSTGRES_APP_PASSWORD`, `SESSION_SIGNING_KEY`, `FIELD_ENCRYPTION_KEY` là thiết yếu, thiếu `BACKUP_ENCRYPTION_KEY` chỉ cảnh báo.

`.env.example` chỉ placeholder; `.env` gitignored. Startup: DB health → migration
one-shot → bootstrap admin → app/workers; không tự migrate destructive khi container
restart. `scripts/dev` hiện có `doctor --target dev|deploy` và `inspect-books`; các
lệnh build/migrate/bootstrap-admin/up/down/test/backup/restore thêm theo task
tương ứng. `down` mặc định không `-v`; reset cần backup và xác nhận rõ. Hướng dẫn
update giữ previous image digest, migration plan và rollback steps.

Inspector chạy network=none, read-only root/input, non-root, drop capabilities,
no-new-privileges, 2 GiB RAM/64 PIDs. Đây là preflight sách local tin cậy, không
thay sandbox ingestion có timeout/retry của T011–T014. OCR khởi đầu concurrency=1;
benchmark chia CPU/RAM/VRAM với Gemma trên máy thật. Embedding chạy batch riêng;
không giả GPU còn rảnh.

## Kết nối Gemma llama.cpp

Người dùng xác nhận Gemma chạy bằng `ghcr.io/ggml-org/llama.cpp:server-cuda`; không
chạy thêm model chat thứ hai và không đổi container hiện tại. T038.1 dùng adapter
`openai_compatible`, base URL kết thúc `/v1`; lấy model ID/alias, context limit,
timeout, JSON capability và GPU/VRAM thực trước smoke.

Ưu tiên API/AI worker cùng một external Docker network riêng với container model,
dùng DNS/cổng thực; thêm cấu hình đó khi biết network và có adapter test. OCR/parser
không nối mạng model; DB/Redis giữ internal network. Nếu đi qua host: `localhost`
trong container là chính container đó; host-gateway không làm dịch vụ chỉ bind
loopback truy cập được. Kiểm bind/firewall ở host, không mở Gemma ra Internet.

Trên Ubuntu, xem tên/image/cổng bằng `docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'`
và network bằng `docker inspect --format '{{json .NetworkSettings.Networks}}' <container>`.
Không gửi toàn bộ inspect/env vì có thể chứa secrets. Adapter kiểm `/health`,
`/v1/models` và một chat smoke nhỏ qua `/v1/chat/completions` theo auth thực của server.

Nguồn: [llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server),
[llama.cpp Docker](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md),
[Docker networking](https://docs.docker.com/engine/network/).

## Secrets và dữ liệu cá nhân

API keys, DB credentials, signing/session secret và field-encryption key qua environment/Compose secrets file ngoài git. Settings chỉ secret_ref allowlisted, UI hiện configured/unconfigured và test result. Secret rotation: version key, re-encrypt background, verify, giữ old key tới khi backup hết retention. Mất encryption key thì restore ciphertext không giải được; recovery key giữ ngoại tuyến riêng.

Bảo vệ profiles bằng application-level authenticated encryption (AES-GCM qua thư viện chuẩn, random nonce, key version); PostgreSQL/object volumes và backup cần full-disk/encrypted storage để bảo vệ facts và derived timestamps. Không tuyên bố database mã hóa toàn bộ chỉ vì một cột đã encrypt. Session tokens random ≥256 bit chỉ hash lưu DB, Argon2id password hash, cookie HttpOnly/SameSite=Strict; production TLS Secure, loopback HTTP local exception ghi rõ. CSRF/Origin check, login rate-limit, audit access.

Đã triển khai (T030, `core/crypto.py`): BirthInput của hồ sơ và input snapshot của lá số mã hóa AES-256-GCM (nonce 96 bit ngẫu nhiên, khóa HKDF-SHA256 từ `FIELD_ENCRYPTION_KEY`), associated data = loại + chủ sở hữu + id bản ghi nên bản mã chép sang dòng/người khác không giải được; `crypto_key_version` là dấu vân tay của khóa dẫn xuất. Sai khóa (restore với .env khác) → 409 `ENCRYPTION_KEY_MISMATCH`, thiếu khóa → 503 `ENCRYPTION_NOT_CONFIGURED`; không bao giờ trả dữ liệu rác. `facts` của lá số (gồm instant và giờ dân sự suy ra) vẫn là JSON thường trong DB: cần ổ mã hóa như trên. Xoay khóa chưa có (cần re-encrypt nền).

RLS và service ACL ở 04; per-job principal/rights snapshot được re-check trước publish; đừng để worker chạy admin bỏ qua quyền của requester. Source download và citations không bypass ACL qua signed URLs dài hạn; localhost dùng authenticated proxy, S3 presigned nếu dùng ≤60s và không đưa key gốc ra UI. Database/storage không public ports.

MCP server của RAG (`/api/v1/mcp/`) tắt mặc định; bật khi có `MCP_TOKEN` (≥ 32 ký tự, so sánh thời gian hằng, ghi vào danh sách che log) và `MCP_USER_EMAIL`. Mọi tool chỉ đọc và chạy với quyền của tài khoản đó: tra lại tài khoản ở mỗi lần gọi (khóa tài khoản là tool dừng ngay), RLS và quyền xem sách áp dụng như trong web. Route nằm sau gateway như phần còn lại của `/api/*`; token đổi bằng cách sửa `.env` và khởi động lại `api`.

## Upload sandbox và prompt injection

Ảnh trang cho duyệt (T046.1) được API render bằng PDFium: chỉ cho trang đã tồn tại, tức nguồn đã được worker trong sandbox mở thành công; một khóa tuần tự hóa mọi lời gọi PDFium trong process, trần 8 triệu pixel; bản sao nguồn tạm có kiểm sha256, giữ tối đa 8 tệp. Magic bytes + extension/MIME cross-check, size/page/pixel/uncompressed limits trước parse. Worker không root, read-only filesystem trừ scratch, drop capabilities, hạn chế CPU/RAM/PIDs/runtime, tắt network cho OCR/parser; model downloader riêng allowlist. Tệp gốc lưu quarantine tới validation. Không active PDF JS, macros, DOCX relationships fetch mạng, shell filename interpolation. Antivirus adapter optional thêm phòng thủ, không thay validation/sandbox.

Document text luôn là quoted untrusted evidence. Prompt template đặt ranh giới, nhưng phòng thủ thật là tool allowlist, schema, ACL, không arbitrary code/network, không access keys và không cấp approve action cho LLM. Red-team PDF chứa “ignore instructions”, fake system text, secret requests, source URL callback, malformed JSON tool arguments. Injection không được tạo rule approved hoặc đọc data khác owner.

## Quyền nội dung sách

Admin ghi rights_status (`unknown/private_reference/licensed/public_domain/restricted`) và chính sách external_processing, export/distribution. Unknown mặc định local-private; không tự bật gửi provider hoặc xuất full text. Chat quote length caps configurable theo quyền, ưu tiên diễn giải với locator. Không scrape/tải thêm sách tự động. Không thể suy quyền thương mại từ việc có PDF. Trước commercialization phải review quyền sách, license parser/model và dependencies; checklist này không là tư vấn pháp lý kết luận.

Đã triển khai (T018): embedding profile khai `locality: local` (CLI `--locality local`) cho máy chủ tự host; profile khác coi là bên ngoài, và stage embed từ chối gửi text của version không bật `external_processing_allowed` (`EXTERNAL_PROCESSING_DENIED`, không gọi provider). Publish chặn version `restricted` hoặc đã withdraw. Withdraw (T019) thu hồi ngay: release active mới không chứa version và `visibility_epoch` tăng; GC chỉ xóa bytes không còn tham chiếu sau thời gian ân hạn và không chạy khi một backup đang giữ khóa bảo trì (T052.1).

## Observability và cost

Structured logs JSON có request_id, run_id, job_id, stage, duration, error_code, version hashes. Đã triển khai (T055): traceback trong log chỉ gồm các frame và tên kiểu exception (cả chuỗi nguyên nhân), không có thông điệp — thông điệp có thể trích dữ liệu người dùng; logger `httpx`/`httpcore` ở mức WARNING vì ghi URL kèm query; log truy cập chỉ có path. Redact passwords, keys, names, full datetime sinh, full chat và book text. Metrics: queues depth/age, page success/review/error %, worker lease expiry, DB pool, disk %, retrieval p95, citation failures, rule unknown/conflicts, tokens/cost/reservations. Admin xem metrics nội bộ; optional Prometheus export restricted.

Đã triển khai (T051, M016, `ops/metrics.py`, `GET /operations/metrics` admin): hàm `bazi_operations_metrics` (SECURITY DEFINER, chỉ trả số đếm/thời điểm, không id/nội dung) gom hàng đợi job sách và run chat (theo trạng thái, tuổi việc chờ lâu nhất), lỗi 24 giờ, phiên bản lỗi ≥ 3 lần, bước xử lý hết hạn lease mà vẫn chạy, trạng thái trang, nhận định bị loại, kết quả quy tắc, usage/token/chi phí 24 giờ, reservation đang giữ, operation jobs, backup gần nhất, có embedding sẵn sàng hay không; tiến trình API thêm pool DB, p50/p95 của 500 lần tìm gần nhất (riêng tiến trình) và dung lượng trống của ổ lưu tệp. Cảnh báo tính lúc đọc: `DISK_LOW` (< 10 % trống), `BACKUP_MISSING`/`BACKUP_OVERDUE` (> 26 giờ), `JOB_REPEATED_FAILURE`, `LEASE_EXPIRED`, `QUEUE_STUCK` (> 30 phút), `BUDGET_EXCEEDED`, `NO_ACTIVE_EMBEDDING`. UI: panel "Vận hành" ở `/settings/system` (tự làm mới 30 s) và danh sách cảnh báo trên tổng quan admin. Chưa có: xuất Prometheus.

Health live không gọi LLM; ready phân biệt essential DB/storage với degraded provider/queue. Alerts local UI: disk low, backup overdue, repeated job fail, budget exceeded, no active embedding cohort. Usage có rounding/currency/pricing version; mặc định budget live calls phải cấu hình trước bật, fixtures chạy offline. Log retention khởi đầu 14 ngày, metrics 90 ngày, run SSE events 7 ngày, audit 180 ngày configurable; không xóa bản nguồn còn cited theo TTL thông thường.

## Backup nhất quán

Release đầu dùng **maintenance backup window** ngắn có thông báo, thay vì hứa hot backup nhất quán khi chưa triển khai WAL. Chặn writes mới, drain/cancel checkpoint workers, đợi transactions hoàn tất, record release pointers/schema/version/config. `pg_dump --format=custom`, manifest blobs ready/cited kèm SHA256, models/config references, migration head, application image/lock hashes, deletion ledger. Copy blobs immutable được manifest tham chiếu, verify checksums, encrypt archive; chỉ báo success sau verification. Không dùng copy trực tiếp thư mục PostgreSQL đang chạy làm backup hợp lệ.

Nếu tương lai thêm hot backup, cần WAL/PITR + coordinated object manifest, ADR riêng; không bỏ requirement backup/restore release hiện tại. Retention mặc định 7 daily+4 weekly trong storage quota; ít nhất một bản ngoài ổ đang chạy. Backup không chứa API secrets; recovery key riêng. Blob orphan cleanup bị khóa trong backup window.

Đã triển khai (T052.1, `backend/app/ops/backup.py`): `scripts/dev backup --dest <thư mục>` chạy `python -m backend.app.cli backup` trong container worker (image app có pg_dump/pg_restore 17 từ kho PGDG, khóa kiểm theo fingerprint). Backup là thư mục `<tên>/`: `db.dump` (pg_dump custom), `objects/..` (mọi blob `ready` theo địa chỉ nội dung, kiểm sha256 + kích thước khi chép) và `manifest.json` (format `bazi-backup-1`, schema head, phiên bản server, sha256 dump, danh sách blob, số dòng của **mọi** bảng, release đang active). Ghi vào `.<tên>.partial`, kiểm `pg_restore --list`, rồi mới đổi tên: thư mục có manifest luôn đầy đủ. Nhất quán mà không chặn ghi: pg_dump đọc đúng snapshot được export từ transaction đã liệt kê objects/đếm dòng; blob bất biến, hàng `objects` chỉ commit sau khi bytes đã lưu; GC giữ cùng advisory lock `bazi.storage.maintenance` nên không xóa gì trong lúc backup (GC thấy khóa → bỏ qua lượt, `BACKUP_RUNNING`). Không chép secret; **chưa mã hóa** ở lớp này — thư mục đích phải nằm trên ổ mã hóa, ngoài các volume, uid 10001 ghi được. Retention, mã hóa archive, API `/operations/backups` thuộc T052 đầy đủ.

Đã triển khai (T052, `ops/archive.py`, `ops/backup.py`): đặt `BACKUP_ENCRYPTION_KEY` (≥ 32 ký tự, giữ một bản ngoại tuyến) thì mọi tệp của backup — dump và từng blob — được mã hóa AES-256-GCM theo khối 4 MiB, khóa dẫn xuất HKDF-SHA256 với salt riêng mỗi backup; dữ liệu liên kết gồm đường dẫn tệp, số thứ tự khối và cờ khối cuối nên sửa/đảo/cắt cụt/chuyển khối sang tệp khác đều bị phát hiện. Manifest ghi scheme, salt, key id (để báo "sai khóa" trước khi đọc dữ liệu) và sha256 cả bản rõ lẫn bản mã của dump; không bao giờ chứa khóa. Không đặt khóa thì backup vẫn chạy nhưng manifest ghi rõ là bản rõ, phải nằm trên ổ mã hóa. Giải mã luôn theo luồng — thẳng vào `pg_restore` qua stdin và thẳng vào kho object — không ghi bản rõ ra đĩa (container chạy root chỉ-đọc). Mỗi backup thành công được ghi vào `backups` (+ `operation_jobs`, manifest là object) để có cảnh báo quá hạn và `GET /operations/backups`; restore không phụ thuộc bảng này. `backup --prune` (CLI và `scripts/dev`) giữ bản mới nhất của 7 ngày và 4 tuần ISO gần nhất, luôn giữ bản mới nhất, bỏ qua thư mục `.partial`. Compose: `env_file` của các service app là `${APP_ENV_FILE:-../.env}` và `scripts/dev --env-file` đặt biến này, nên container đọc đúng file được chỉ định (trước đó luôn đọc `.env` thật); preflight chỉ nhận `BACKUP_ENCRYPTION_KEY` (theo tên, giá trị từ môi trường tiến trình).

## Restore runbook bắt buộc kiểm thử

Khi mất toàn bộ DB, dùng `scripts/dev restore --manifest <backup-manifest-path>` từ host để dựng recovery stack; không phụ thuộc bảng backups trong DB đã mất. Manifest ngoài archive tự mô tả encryption version/checksums, không chứa key. API restore chỉ là giao diện cho trường hợp server quản trị còn hoạt động.

1. Preflight backup checksum, đúng key version, disk đủ, migration/app compatible; chỉ báo pass khi đọc được manifest và giải mã thử. Fresh preflight token hết hạn 15 phút.
2. Confirmation tên backup và phạm vi mất dữ liệu; tạo safety backup hiện tại nếu có thể. Dừng write/API workers, dùng **volumes mới** thay vì ghi đè live ngay.
3. Restore DB bằng pg_restore, blobs theo manifest, encryption refs/config; áp deletion ledger sau backup để không phục hồi dữ liệu đã yêu cầu xóa. Chưa khởi worker cho đến khi pointers/rights/objects verify.
4. Chạy orphan/missing-object check, foreign-key integrity, open source pages, chart deterministic hash, retrieve known evidence, replay conversation citations, requeue unfinished jobs bằng DB/outbox; không phát lại việc có side effect đã hoàn thành.
5. Index vector lexical thiếu có thể rebuild theo đúng model/profile/version, vẫn chưa declare ready đến khi coverage đạt. So checksum và synthetic tests, chuyển volumes/cổng khi pass; nếu fail giữ system cũ.
6. Ghi restore report và measured RTO/RPO. Mục tiêu RPO≤24h theo daily backup, RTO phải đo thực tế; chưa cam kết số phút.

Đã triển khai (T053.1): `scripts/dev restore-preflight --manifest …` (container không mạng, read-only: sha256 dump, `pg_restore --list`, rehash mọi blob, schema head có trong code) và `scripts/dev restore --manifest … --confirm <tên backup>` luôn dựng **Compose project mới** (`bazi-restore`, volume riêng; từ chối project đang chạy). CLI restore từ chối DB đã có bảng (`TARGET_NOT_EMPTY`), sai tên xác nhận, preflight lỗi hoặc thiếu chỗ ổ; tạo role `bazi_runtime` nếu thiếu; chép blob trước (idempotent) rồi `pg_restore --single-transaction`; kiểm lại số dòng mọi bảng, schema head, release active và từng blob trong store mới; báo cáo thời gian restore (một phần RTO) và tuổi backup (RPO). Sau đó `create-runtime-login`, chạy app ở cổng khác để kiểm rồi mới chuyển. Đã thử trên máy dev: project tạm → backup → restore vào project mới (82 bảng, blob khớp) → xóa volume tạm. Chưa có ở T053.1: deletion ledger, kiểm chart/chat, API restore.

Đã triển khai (T053): sau pg_restore, `post_restore_checks` (runbook bước 4) kiểm lại mọi đoạn trích dẫn khớp text trang, mọi lá số khớp hash facts, con trỏ kho trỏ tới release `active`, sha256 từng tệp nguồn sách trong kho mới, và đếm job dở dang mà watchdog sẽ chạy tiếp; sai → `VERIFY_FAILED`, báo cáo restore ghi các số này. Ledger xóa (T049) áp lại khi có `--deletion-ledger`. `scripts/dev drill --manifest … --confirm …` diễn tập: restore vào project `bazi-drill` (volume riêng) rồi gỡ project đó cùng volume (kể cả volume của profile `app`), không bao giờ là project đang chạy. Đã diễn tập trên máy dev 18/10/2026: project tạm `bazi-smoke` (migrate tới M016, admin) → backup mã hóa (được ghi nhận) → preflight không khóa bị từ chối, có khóa qua → drill restore 83 bảng + kiểm tra trong 13 s → gỡ cả hai project; volume `bazi-ai_*` không bị đụng. DB tạm này không có sách/lá số — nội dung (sách, trích dẫn, lá số, blob mã hóa, khóa sai, tệp hỏng) được kiểm bằng test tích hợp chạy trong image test có pg_dump 17. Chưa có: API restore (cố ý — restore chạy từ host), đo RTO với dữ liệu thật trên Ubuntu.

## Deletion

Soft delete ẩn ngay, stop new reads/runs, async hard delete private text và related derived artifacts theo reference graph. Public book content withdrawal ưu tiên quyền over historical reproducibility. Citation cũ hiển thị tombstone, không excerpt còn sót. Cache eviction và vector deletion nằm cùng operation checklist; test canary không tìm lại text đã xóa. Backup giữ tối đa retention công khai, ledger phục vụ restore. Audit chỉ retained actor/action/hash ID tối thiểu, không nội dung yêu cầu xóa.

Đã triển khai (T049, M015, `auth/erasure.py`): `POST /auth/erasure` (người dùng tự xóa: gõ đúng email + mật khẩu) và `POST /users/{id}/erasure` (admin: gõ đúng email người kia) xóa **cứng, đồng bộ** mọi dữ liệu riêng của một người qua hàm `bazi_erase_owner` (SECURITY DEFINER vì RLS che dữ liệu người khác): lá số, phân tích + trace, hồ sơ sinh, hội thoại/tin nhắn/claim/citation/run/sự kiện, gói bằng chứng, ca mẫu riêng, cài đặt cá nhân, feedback, bản replay idempotency (có thể chứa dữ liệu sinh) và session. Usage giữ lại để tính ngân sách nhưng bỏ liên kết run (không có nội dung). `delete_account`: giữ hàng user cho tác giả tri thức đã duyệt/audit nhưng thay email (`deleted-<id>@invalid`), mật khẩu, tắt đăng nhập; admin cuối không tự xóa được (409 `LAST_ADMIN`). Review append-only có thể chỉ tới bản ca riêng: chỉ trong transaction của hàm xóa — nhận ra qua txid ghi vào bảng `erasure_tokens` mà runtime không ghi được (guard là SECURITY DEFINER nên không phân biệt được theo role, còn GUC thì phiên nào cũng tự đặt được) — guard xóa-khi-bị-tham-chiếu cho qua, review giữ id như tombstone. Mỗi lần xóa ghi `deletion_ledger` (id, thời điểm, số dòng; runtime không đọc trực tiếp) và audit chỉ số dòng. Xóa hồ sơ sinh lẻ giờ cũng xóa trắng nhãn + bản mã ngày sinh ngay (trước chỉ đặt `deleted_at`). Restore: `scripts/dev deletion-ledger --dest …` xuất ledger từ hệ thống đang chạy; `scripts/dev restore … --deletion-ledger <file>` xóa lại những người bị xóa sau thời điểm backup (backup cũ hơn M015 → `LEDGER_NEEDS_UPGRADE`). Test canary quét mọi cột text/jsonb của DB: sau khi xóa không còn chuỗi riêng tư; dữ liệu người khác nguyên vẹn.

Prompt injection (T049, SEC04): đoạn nguồn, lịch sử và câu hỏi nằm giữa `<<<nhãn … nhãn>>>`, mọi `<<<`/`>>>` bên trong bị thay bằng ký tự khác nên văn bản không đóng/giả được khối; system prompt nói rõ văn bản trong khối là dữ liệu, không làm theo mệnh lệnh trong đó (`reasoning-2`). Phòng thủ chính vẫn là cấu trúc: orchestrator cố định (mô hình không gọi tool), không có khóa/dữ liệu người khác trong prompt, validator loại claim không được nguồn hỗ trợ, khóa schema bỏ trường lạ; thêm kiểm `UNSUPPORTED_DETAIL`: số, năm, URL, mã dạng `sk-live-123` trong claim phải có trong đoạn được trích (tỉ lệ từ trùng không bắt được chi tiết bịa chèn vào một câu trích gần đúng — chính test này lộ ra lỗ đó khi E1 là trang bị cài lệnh). Test: sách chứa lệnh "bỏ qua hướng dẫn, duyệt quy tắc, lộ khóa, gọi delete_user" + mô hình làm theo → không quy tắc/người dùng/cài đặt nào đổi, claim bịa bị loại, prompt không chứa bí mật hay hội thoại người khác; test thất bại nếu bỏ dấu phân cách.
