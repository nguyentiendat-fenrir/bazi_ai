# 03 · Kiến trúc và ranh giới module

## Hiện trạng và đích

Đang chạy: Compose có PostgreSQL, Redis và `corpus-inspect` chạy một lần; backend
mới có foundation T003 (`backend/app`: config, logging, errors, health), chưa có
frontend. Topology dưới đây là **đích dài hạn**; service chỉ được
thêm cùng implementation và tests, không tham chiếu module chưa có. Image mang
code/lock; sách mount read-only; DB/objects/checkpoints ngoài Git.

Thứ tự xây theo [14](14_ROADMAP.md): library → jobs → review → search/evaluation,
sau đó calculation/DSL/chat. Gemma chạy ngoài Compose dự án, nối qua provider
`openai_compatible` ([12](12_SECURITY_OPERATIONS.md#kết-nối-gemma-llamacpp)). LLM
không âm thầm sửa chữ OCR; mọi đề xuất là draft cần nguồn và reviewer.

## Topology

```mermaid
flowchart TD
  UI["Next.js / localhost:3000"] --> API["FastAPI modular monolith"]
  API --> DB["PostgreSQL + pgvector"]
  API --> OBJ["ObjectStore adapter"]
  API --> Q["Redis broker"]
  Q --> W["Celery workers"]
  W --> DB
  W --> OBJ
  API --> AI["Model adapters"]
  W --> AI
```

Một repository, một backend package, migrations dùng chung. API process không chạy OCR/model nặng. Worker profiles `ingest`, `ocr`, `ai`, `maintenance`; không tách network service nghiệp vụ. UI (T043.1): gateway Caddy tại một cổng loopback (`GATEWAY_PORT`, mặc định 3000), `/api/*` đến service `api` (uvicorn), còn lại service `frontend` (Next.js standalone); SSE tắt buffering; chỉ gateway có cổng host. Database/Redis/object volume không expose host port mặc định. Dev override được bind loopback riêng, không `0.0.0.0`.

## Stack chốt và điều chỉnh

Python 3.12 làm baseline tương thích; PostgreSQL 17 + pgvector từ 0.8 để có iterative scans; FastAPI/Pydantic2/SQLAlchemy2/Alembic; Next.js + TypeScript; Redis + Celery. Phiên bản đã khóa và license matrix ghi ở [decision log](15_ARCHITECTURE_DECISIONS.md#decision-log); không dùng “latest”. Lock tất cả transitive dependencies, image digest và model revision sau smoke.

Storage: `ObjectStore` interface với `put_if_absent`, `get_stream`, `stat`, `delete`, `list_manifest`, `copy_verified`; local filesystem volume là mặc định, S3-compatible adapter cùng contract. Blob key do server tạo theo hash/UUID, không nhận path từ client. Đã triển khai (T007, `backend/app/storage`): key `objects/<2 hex>/<sha256>` khớp allowlist; ghi stream qua `staging/` rồi promote atomic (rename cục bộ / copy S3), giới hạn `MAX_UPLOAD_BYTES` kiểm khi đang stream; đọc theo range; `copy_verified` băm lại khi chép giữa adapter. Xóa đi qua DB trước (FK RESTRICT chặn object còn được tham chiếu), blob chỉ xóa sau commit; blob không có row là orphan cho sweep. MinIO Community không là dependency bắt buộc (ADR-03). Tài liệu lớn được stream, không load nguyên sách vào RAM.

PyMuPDF dùng cho audit hiện tại và là parser option khi giấy phép cho phép; extraction native mặc định dùng PDFium qua pypdfium2 (ADR-22), Docling layout là profile tùy chọn sau benchmark. PyMuPDF adapter là optional profile; không coi tách process là cách né nghĩa vụ license. OCRmyPDF/Tesseract là worker option cho scanned PDF; Tesseract vùng ảnh hỗ trợ `vie+eng`, thêm `chi_sim/chi_tra` nếu nguồn cần. Model OCR dạng VLM (ví dụ PaddleOCR-VL) chỉ là ứng viên benchmark ở T012, phải so trên trang gán nhãn và tính chung VRAM với Gemma; không mặc định khi chưa có ADR. Reranker/embedding model có registry, không hardcode provider trong code.

## Module contracts nội bộ

| Module | Sở hữu | Đầu vào → đầu ra | Không được làm |
|---|---|---|---|
| auth/settings | users, session, permissions, runtime profiles | principal → policy/secret reference | Trả secret về browser |
| storage | immutable blobs, checksums | stream → object id | Dùng tên upload làm đường dẫn |
| documents | books, versions, pages, corrections | object → versioned source | Duyệt rule tự động |
| ingestion | job/stage/lease/outbox/publication | version+pipeline → snapshot | Ghi đè nguồn đang được citation dùng |
| knowledge/cases | concepts, assertions, rules, evidence, review | candidates → approved revisions | Đồng nhất school không có duyệt |
| retrieval | lexical/vector/rerank/context | QuerySpec → EvidenceBundle | Tự sinh trang nguồn |
| calculation | time/calendar/pillars/cycles | BirthInput+policy → ChartFacts | Gọi LLM |
| rules | DSL validation, DAG, tri-valued evaluation | facts+ruleset → RuleTrace | eval/exec/Python dynamic |
| reasoning/chat | run orchestration, claims, sessions, cost | context+facts+evidence → Answer | Sửa facts hoặc publish tri thức |
| evaluation/operations | datasets, runs, reports, backups | scenario → measured results | Tự chấm thay chuyên gia |

## Transaction và event

API mutation ghi DB + `outbox_events` trong cùng transaction, sau đó dispatcher đẩy Celery. Worker lock job stage/page, nhận lease có fencing token, ghi output vào staging key, kiểm tra token còn hiện hành trước commit. Outbox có event_id unique; consumer dedupe bằng `processed_events`. Không giả định delivery exactly-once. Watchdog tìm lease hết hạn và requeue từ checkpoint; Redis restart không làm mất danh sách job cần chạy.

Khởi tạo kho trống không cần tạo fake release/model vectors: chưa có row active_corpus thì search trả empty_corpus, chat run corpus_release_id=null; tables, ontology taxonomy và chart vẫn dùng được. Embedding profile mặc định được cài ở task indexing; model bytes tải theo cấu hình, không bắt buộc để mở UI.

Đọc snapshot: một `corpus_release` ghim mapping version→generation; release có lifecycle BUILDING/READY/ACTIVE/RETIRED. Active pointer chuyển trong một transaction sau khi tất cả membership và index sẵn sàng. Truy vấn lọc release_id. OCR correction tạo revision mới, generation mới, chunks mới trong cửa sổ ảnh hưởng; phần không đổi tái dùng revision/chunk IDs qua membership. Không ghép text mới với embedding cũ.

Hai mức version tách biệt: (1) ingest generation của một book version; (2) corpus release chứa nhiều generation. Rule set và ontology revision độc lập với corpus release; chat run ghi cả ba. Chuyển embedding profile xây release mới đầy đủ; query vector và stored vectors phải cùng profile/model dimension. Không trộn vector khác model dù cùng số chiều.

## Dữ liệu cá nhân và chi phí

Chart computation local. API provider chỉ nhận facts đã bỏ tên/định danh và đoạn nguồn được phép; sách mặc định `external_processing_allowed=false` đến khi admin lựa chọn trong upload policy. LLM giới hạn token, timeout, retry, budget reservation, không gửi cả sách cho mỗi câu hỏi. Retry provider có thể vẫn tính phí; log estimate và actual riêng.

## Quy mô trên máy cá nhân

Khởi đầu CPU OCR concurrency=1, ingest=2, prefetch=1 cho long jobs; embedding batching theo token budget. Đây là tham số ban đầu để benchmark, không hứa throughput. Tài nguyên Ubuntu chia với Gemma; `doctor --target deploy` đọc RAM/disk thực tế thay vì mặc định cấu hình có sẵn. GPU không bắt buộc. PDF 100–500 nghìn trang chạy theo queue và disk budget, không xử lý tất cả trong một transaction. Chính sách pause khi disk dưới ngưỡng (mặc định 15% hoặc 10 GiB, lấy giá trị lớn hơn) và resume sau khi đủ dung lượng.
