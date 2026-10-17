# 15 · Architecture Decision Records

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
| 22 | FIXED | Native PDF extraction dùng PDFium (pypdfium2, Apache-2.0/BSD) làm backend mặc định sau adapter; Docling layout pipeline là profile tùy chọn khi đã benchmark — [chi tiết](#adr-22-chi-tiết) | Không kéo torch/model layout vào worker mặc định; không dùng pypdf cho extraction |
| 21 | FIXED | Kho tri thức trước; Windows dev native, Ubuntu 22.04 runtime cùng host Gemma — [chi tiết](#adr-21-chi-tiết) | Không ép WSL trên máy dev; không đổi schema/API |

## ADR-21 chi tiết

**ACCEPTED 17/10/2026 theo yêu cầu chủ dự án, T057.** Thay thứ tự T001→T056 bằng lộ trình ở
[14](14_ROADMAP.md) và bỏ gate bắt buộc WSL trên máy dev. Giữ schema/API, source preservation và release gates.

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
CASE tự thành nguồn chuẩn; xóa evidence để ít file. Rollback: revert commit
T057 `49636dd`, không chạm input/volumes; các commit sau đó (bỏ TASKS/AGENTS/reports,
tái cấu trúc docs) độc lập, revert riêng nếu cần. Không migration/DTO mới.

## ADR-22 chi tiết

**ACCEPTED 17/10/2026, T011.** Bổ sung ADR-12 (giữ nguyên ý "parser adapters, PyMuPDF chỉ là tùy chọn"). Đo trên 4 PDF thật (815 trang): pypdf tách sai chữ có dấu ("tinh th ần"); PDFium trả đúng ("tinh thần", "có thể"), 1–3,5 s/cuốn, 0 ký tự U+FFFD, có bbox từng ký tự, font, cỡ, độ đậm và **màu** (Tử Bình phân lớp bình chú bằng màu), nhãn trang và vùng ảnh. Docling cũng dùng PDFium cho đường native; pipeline đầy đủ của Docling cần torch và model layout (GB, tranh VRAM với Gemma) và chưa benchmark trên gold. Quyết định: stage `validate`/`extract` dùng `backend/app/ingestion/pdf_native.py` (pypdfium2 5.14 / PDFium 156); `PARSER_VERSION` nằm trong idempotency key và layout của revision nên đổi backend tạo revision/generation mới. Docling layout là profile thêm sau khi so trên bộ trang gán nhãn (T014). Rollback: đổi handler của pipeline profile, revision cũ giữ nguyên.

## Nguồn kỹ thuật chính thức và điều đã sử dụng

- [pgvector README](https://github.com/pgvector/pgvector): ANN filtering có thể giảm số kết quả; hỗ trợ iterative scans và exact search. Căn cứ thiết kế filter-aware retrieval, không phải benchmark của dự án.
- [PostgreSQL dictionaries](https://www.postgresql.org/docs/current/textsearch-dictionaries.html): cơ chế text search dictionaries; cấu hình `simple`/normalization là lựa chọn dự án, không gọi là BM25 tiếng Việt.
- [Celery task documentation](https://docs.celeryq.dev/en/v5.5.0/userguide/tasks.html): late acknowledgment cần idempotent task và còn có các trường hợp worker termination; dùng thêm durable DB recovery.
- [Docling pipeline options](https://docling-project.github.io/docling/reference/pipeline_options/): OCR/table/layout tăng chi phí tài nguyên; profile/timeout cần cấu hình. Không có bảo đảm parse đúng mọi bảng mệnh lệ.
- [MinIO official repository](https://github.com/minio/minio): trang hiện trạng ghi archive 25/04/2026 và no longer maintained. Do đó loại khỏi mandatory local dependencies, vẫn giữ storage interface S3-compatible.
- [PyMuPDF documentation](https://pymupdf.readthedocs.io/): AGPL/commercial license; cần kiểm điều kiện sử dụng khi đóng gói thương mại, không đưa ra kết luận pháp lý thay chuyên gia.
- [Docker Engine trên Ubuntu](https://docs.docker.com/engine/install/ubuntu/): runtime đích theo ADR-21; repo nằm trên filesystem Linux. Giới hạn RAM cụ thể là dự trù phải đo trên máy thật.
- [lunar-python repository](https://github.com/6tail/lunar-python): thư viện tính lịch đang được adapter dùng; audit thực thi dùng bản 1.4.4 trích từ archive, không thay bằng master web.
- [sxtwl repository](https://github.com/yuangu/sxtwl_cpp): ứng viên đối chiếu, không coi độc lập hoàn toàn với mọi thuật toán cùng gốc ShouXing.
- [NOAA Solar equations](https://gml.noaa.gov/grad/solcalc/solareqns.PDF): fractional-year reference dùng để phát hiện pha góc EOT sai trong code cũ. Chỉ là công thức xấp xỉ đối chiếu, không là chứng nhận thiên văn chính xác vô hạn.
- [HKO solar terms](https://www.hko.gov.hk/en/gts/astronomy/Solar_Term.htm): nguồn oracle thời điểm tiết khí cần thu thập ở implementation. Trang năm 2024 cụ thể không truy cập được trong audit này; không báo đã có gold HKO đầy đủ.

## Decision log

Mỗi entry có date, task, chosen setting, evidence, rejected variants và rollback.
Các task cần ghi: T002 versions/license; T025/T035 dataset/gold; T027–T030
policy/oracle/sai số; T036–T037 model/chunk/rerank ablations; T051 tài nguyên/
throughput/latency; T053 measured restore. Thay model không đổi business schema;
thêm collection/profile/release chạy từ admin qua registry được kiểm soát.

- **11/10/2026 · T002 (chưa nghiệm thu):** khóa Python 3.12 + uv (`uv.lock`, 52
  packages); image upstream ghim digest SHA256 trong `infra/compose.yaml` và
  Dockerfile, không dùng `latest`. Smoke thực: PostgreSQL 17.11 + pgvector 0.8.7,
  Redis 8.8.3, temp table ghi/đọc và Redis `PONG`. License: Docling code MIT
  (weights license riêng, khóa khi làm T011); PyMuPDF AGPLv3/commercial → chỉ adapter
  tùy chọn; OCRmyPDF MPL-2.0, Tesseract Apache-2.0 → OCR profile T012;
  multilingual-e5-base/bge-m3 model card MIT → ứng viên ADR-16; Redis 8 chọn
  AGPLv3/RSALv2/SSPLv1 → dùng image upstream không sửa, review trước phân phối;
  lunar-python MIT. Loại: image không digest, `latest`, MinIO bắt buộc, PyMuPDF mặc
  định. Rollback: checkout trước `c9e709a`, giữ volumes; không có migration. Phần
  Next 16/Caddy trong T002 đã bỏ ở T057. Còn thiếu: smoke trên Ubuntu 22.04 thật.
- **18/10/2026 · T020:** trường phái của sách gán theo version hoặc khoảng trang vật lý (ổn định qua generation), không theo section path (đổi khi heading đổi); phân loại ghi vào generation để snapshot đã publish không trôi, đổi scope là reprocess (rẻ vì mọi unit tái dùng). Alias gắn revision concept; revision mới chép alias làm draft và chỉ tự duyệt lại cái đã duyệt trước đó. Loại: cột school trên books (một sách nhiều trường phái), phân loại tính lúc query (trôi theo scope hiện tại), sửa alias tại chỗ. Rollback: revert commit và `alembic downgrade 0009_m009_batch_items` (chỉ khi chưa có review cho scope).
- **18/10/2026 · T019:** sự kiện job ghi trong cùng transaction với thay đổi (không có "stage done" cho việc đã rollback); seq cấp dưới khóa hàng job. Retry = job con, unit thành công luôn dùng lại, unit lỗi của version được thử lại từ đầu; dựng lại toàn bộ là `/process`. Reprocess nối bản sửa mới nhất kế thừa từ revision trích xuất (không vá lên trích xuất parser khác). Withdraw và resolve review chạy đồng bộ; resolve page đổi state revision rồi rebuild gia tăng, định danh chunk thêm `quality_state`. Loại: withdraw bất đồng bộ (cửa sổ nội dung đã thu hồi vẫn hiện), xóa nội dung khi withdraw, GC không thời gian ân hạn. Rollback: revert commit; events/review/release là dữ liệu và ở lại.
- **18/10/2026 · T018:** publish đồng bộ (trả release, không trả operation 202) vì chỉ ghi membership và đổi con trỏ; mọi publish/activate tuần tự qua một khóa corpus nên release mới luôn dựng trên release đang active. Generation chỉ vào release sau khi stage `publish` niêm phong (`ready` + manifest). Trạng thái `published`/`superseded` của generation theo membership của release active; membership mới là nguồn sự thật. Profile embedding không khai `locality: local` bị coi là bên ngoài (mặc định an toàn). Loại: operation bất đồng bộ cho publish (thêm polling không cần), activate không CAS (ghi đè publish đồng thời), mặc định provider là local. Rollback: revert commit; release/membership đã tạo là dữ liệu, con trỏ có thể activate lại release `ready` khác.
- **17/10/2026 · T017:** sửa trang = revision mới bất biến; ETag của trang là id revision mới nhất, bắt buộc If-Match + `base_revision_id` + Idempotency-Key. Rebuild là generation gia tăng chạy lại cả pipeline nhưng tái dùng theo idempotency stage, chunk (text + spans) và vector (content hash), nên chỉ trang sửa được re-chunk và chỉ text mới được embed. Bản sửa khi rebuild còn queued được gộp; khi job đang chạy thì từ chối 409 thay vì để job bỏ sót. Flag `SOURCE_CHANGED` theo khoảng ký tự bị sửa, không tự cập nhật nghĩa đã duyệt. Loại: sửa tại chỗ revision cũ (citation trôi), dựng lại toàn sách mỗi lần sửa (re-embed mọi chunk), flag cả trang. Kèm theo: parser `pdfium-native-5` (tiêu đề chương chứa từ lá số không còn bị coi là hàng lá số; Tử Bình 580 → 583 section). Rollback: revert commit; revision sửa là dữ liệu và ở lại, generation gia tăng có thể withdraw.
- **17/10/2026 · T013:** bản dựng DOCX bằng LibreOffice 7.4.7.2 (`libreoffice-writer-nogui`, Debian bookworm) + `fonts-dejavu-core`, `fonts-noto-cjk` trong image `app`; phiên bản renderer nằm trong input hash nên đổi renderer tạo revision mới. PDF bản dựng không byte-ổn định (timestamp), nên định danh revision theo text DOCX, bản dựng chỉ là object hiển thị. Loại: dùng text trích từ bản dựng làm nguồn (mất số thứ tự/anchor), bịa số trang khi không định vị được.
- **17/10/2026 · T012:** OCR = Tesseract 5.3.0 từ Debian bookworm (`tesseract-ocr-vie/eng/chi-sim/chi-tra`) trong image `app` (base Python ghim digest; gói apt theo bookworm, phiên bản ghi trong `ocr_engine.version` của mỗi revision). Chọn vì Apache-2.0, chạy CPU, không tranh VRAM với Gemma; VLM OCR (PaddleOCR-VL…) chỉ là ứng viên benchmark trên trang gán nhãn. Loại: OCR mọi trang, ghi đè text native. Rollback: bỏ `OcrStage` khỏi pipeline, revision native vẫn còn.
- **17/10/2026 · T057:** Compose chỉ còn PostgreSQL, Redis, `corpus-inspect`
  (non-root, read-only, network none); bỏ scaffold frontend/Caddy; doctor tách
  `dev`/`deploy`; pypdf ở dependency group `corpus` chỉ cho preflight. Inspector cho
  cùng SHA256 bảy file trên Windows và Linux. Rollback: revert `49636dd`.
