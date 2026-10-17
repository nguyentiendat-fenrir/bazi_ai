# 15 · Architecture Decision Records

## ADR-21 — Kho tri thức trước; Windows dev / Ubuntu runtime

**ACCEPTED 17/10/2026 theo yêu cầu chủ dự án, T057.** Thay thứ tự T001→T056 và
gate bắt buộc WSL trên máy dev. Giữ schema/API, source preservation và release gates.

- Windows native chạy code/tests; Ubuntu 22.04 chạy Docker Engine/Compose. Image
  mang code/lock, dữ liệu ngoài Git. Doctor tách `dev` và `deploy`.
- Giữ FastAPI, Next.js khi có UI thật, PostgreSQL/pgvector/FTS, Redis/Celery,
  immutable sources, human review và citation. Kho nguồn/tra cứu đi trước lá số.
- Người dùng xác nhận Gemma qua `ghcr.io/ggml-org/llama.cpp:server-cuda`; chọn
  adapter `openai_compatible`, không cài model thứ hai. Endpoint/model/VRAM chưa biết.
- pypdf thuộc dependency group `corpus` chỉ để preflight, không thay Docling
  layout parser/OCR production ADR-11/12; không có publish hoặc HTTP API mới.
- Bỏ scaffold frontend/proxy và service command trỏ module vắng mặt. Thêm lại
  cùng implementation/tests. Giữ backend lock cho foundation kế tiếp.
- Giữ sách, legacy, manifest kiểm nguồn và contracts kỹ thuật.

Phương án loại: ép WSL; OCR mọi trang; dùng Gemma chat làm embedding mặc định;
CASE tự thành nguồn chuẩn; xóa evidence để ít file. Rollback bằng revert commit
`49636dd`, không chạm input/volumes. Không migration/DTO mới.

Trạng thái `FIXED` là quyết định của đặc tả này, thay đổi cần ADR diff; `EXPERIMENT` là tham số phải đo, không phải lý do bỏ module. Ngày đối chiếu nguồn kỹ thuật 10–11/10/2026. Patch versions xác minh lại ở T002.

| ADR | Trạng thái | Quyết định và lý do | Phương án loại / hệ quả |
|---|---|---|---|
| 01 | FIXED | Modular monolith FastAPI + worker cùng package; Next.js riêng presentation | Không microservices/Kubernetes; tránh vận hành phân tán không cần thiết |
| 02 | FIXED | PostgreSQL+pgvector+FTS/trgm giữ transactional metadata và hybrid search | Chưa dùng Neo4j/Elasticsearch/vector DB riêng; query graph bằng relational tables |
| 03 | FIXED | Local filesystem ObjectStore mặc định + S3 adapter trong release | Không bắt buộc MinIO Community archived; không thay thành một cụm storage mới phức tạp |
| 04 | FIXED | Giữ legacy chart qua adapter; sửa lỗi có regression, không viết lại toàn bộ | Không tin thư viện mù quáng; policy và independent oracle bắt buộc |
| 05 | FIXED | Immutable page revisions, chunk source spans, per-book generations và corpus releases | Không overwrite OCR text/vector đang cited; chấp nhận chi phí disk/GC |
| 06 | FIXED | Celery/Redis là execution; DB outbox/leases/idempotency là truth | Không tuyên bố exactly-once từ broker; không chỉ Redis state |
| 07 | FIXED | Scoped ontology/rules và author layers; explicit approval | Không gộp Thể–Dụng với Dụng Thần; không AI autoapprove |
| 08 | FIXED | Typed JSON DSL, tri-valued logic, no arbitrary code | Không eval Python LLM; rule ordering không tự giải mâu thuẫn |
| 09 | FIXED | LLM giải thích facts/rules/evidence đã kiểm; citations backend-resolved | Không LLM tính lịch, bịa page, hoặc tự sửa chart |
| 10 | FIXED | Streaming validated claims + progress SSE, durable replay | Không raw streaming token chưa kiểm citation; thêm độ trễ có chủ đích |
| 11 | FIXED | Parser adapters, native first, OCR per-page/region, docx canonical render | Không OCR mọi trang; không coi DOCX có page index ổn định |
| 12 | FIXED | PyMuPDF optional license-reviewed; Docling parser profile default | Không giả mọi thư viện free đồng nghĩa dùng thương mại không điều kiện |
| 13 | FIXED | Core workflows không phụ thuộc có sách/model API | Không hardcode ba PDF; no-model/empty-corpus states typed |
| 14 | FIXED | Backup maintenance window+verified manifest+clean-volume restore | Chưa yêu cầu hot backup/PITR phức tạp; vẫn bàn giao restore hoàn chỉnh |
| 15 | FIXED | Gregorian range 1900–2100; explicit calendar IDs; policies versioned | Không âm thầm dùng Chinese lunar làm Vietnamese lunar; unsupported có lỗi rõ |
| 16 | EXPERIMENT | Embedding multilingual-e5-base vs bge-m3/API eligible | Chọn theo gold Việt/Hán Việt, memory/cost/license; không đo thì không gọi “tốt nhất” |
| 17 | EXPERIMENT | Semantic chunk khởi đầu 350–700 tokens, overlap 60–100, bounded tables | Benchmark retrieval+source continuity; không cam kết đúng bằng token count |
| 18 | EXPERIMENT | Top lexical/vector 80, fused 40, context 8/6k tokens, RRF k=60 | Ablations và p95/recall quyết định; school/ACL filters cố định |
| 19 | EXPERIMENT | OCR DPI 200–300, concurrency1; worker ingest2; resource quotas | Benchmark trên máy thực, no GPU requirement |
| 20 | EXPERIMENT | Reranker multilingual local hoặc API, timeout fallback | Module rerank bắt buộc, lựa chọn model không cố định vào provider |

## Nguồn kỹ thuật chính thức và điều đã sử dụng

- [pgvector README](https://github.com/pgvector/pgvector): ANN filtering có thể giảm số kết quả; hỗ trợ iterative scans và exact search. Căn cứ thiết kế filter-aware retrieval, không phải benchmark của dự án.
- [PostgreSQL dictionaries](https://www.postgresql.org/docs/current/textsearch-dictionaries.html): cơ chế text search dictionaries; cấu hình `simple`/normalization là lựa chọn dự án, không gọi là BM25 tiếng Việt.
- [Celery task documentation](https://docs.celeryq.dev/en/v5.5.0/userguide/tasks.html): late acknowledgment cần idempotent task và còn có các trường hợp worker termination; dùng thêm durable DB recovery.
- [Docling pipeline options](https://docling-project.github.io/docling/reference/pipeline_options/): OCR/table/layout tăng chi phí tài nguyên; profile/timeout cần cấu hình. Không có bảo đảm parse đúng mọi bảng mệnh lệ.
- [MinIO official repository](https://github.com/minio/minio): trang hiện trạng ghi archive 25/04/2026 và no longer maintained. Do đó loại khỏi mandatory local dependencies, vẫn giữ storage interface S3-compatible.
- [PyMuPDF documentation](https://pymupdf.readthedocs.io/): AGPL/commercial license; cần kiểm điều kiện sử dụng khi đóng gói thương mại, không đưa ra kết luận pháp lý thay chuyên gia.
- [Docker Desktop WSL best practices](https://docs.docker.com/desktop/features/wsl/best-practices/): dùng filesystem Linux cho workload Linux và WSL integration. Các giới hạn RAM cụ thể là dự trù phải đo.
- [lunar-python repository](https://github.com/6tail/lunar-python): thư viện tính lịch đang được adapter dùng; audit thực thi dùng bản 1.4.4 trích từ archive, không thay bằng master web.
- [sxtwl repository](https://github.com/yuangu/sxtwl_cpp): ứng viên đối chiếu, không coi độc lập hoàn toàn với mọi thuật toán cùng gốc ShouXing.
- [NOAA Solar equations](https://gml.noaa.gov/grad/solcalc/solareqns.PDF): fractional-year reference dùng để phát hiện pha góc EOT sai trong code cũ. Chỉ là công thức xấp xỉ đối chiếu, không là chứng nhận thiên văn chính xác vô hạn.
- [HKO solar terms](https://www.hko.gov.hk/en/gts/astronomy/Solar_Term.htm): nguồn oracle thời điểm tiết khí cần thu thập ở implementation. Trang năm 2024 cụ thể không truy cập được trong audit này; không báo đã có gold HKO đầy đủ.

## Decision log cần điền khi triển khai

T002 ghi resolved package/image versions/license matrix; T025/T035 ghi dataset/gold; T027–T030 ghi policy/oracle/sai số; T036–T037 ghi model/chunk/rerank ablations; T051 ghi tài nguyên/throughput/latency; T053 ghi measured restore. Mỗi entry có date, author, evidence, chosen setting, rejected variants và rollback. Thay model không đổi business schema; thêm collection/profile/release có thể chạy từ admin qua registry được kiểm soát.
