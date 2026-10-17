# 05 · Document Processing Engine

## Corpus hiện tại

Kiểm kê 17/10/2026 (T057) bằng [`scripts/inspect_corpus.py`](../scripts/inspect_corpus.py):
pypdf quét text mọi trang PDF, thống kê DOCX/Markdown chỉ đọc. Đây là preflight,
không phải parser layout/OCR hay gate accepted/publish; cờ <100 ký tự/U+FFFD chỉ để
xem lại, đủ chữ vẫn có thể sai bảng/ảnh/reading order. Số ký tự pypdf không thay số
đo PyMuPDF của audit [02](02_SOURCE_CODE_AUDIT.md#6-pdf-audit). Cả bốn PDF là PDF số có
lớp chữ native; OCR chỉ cần cho vùng ảnh và sách scan sau này.

| Nguồn | Đo thực tế | Cách dùng |
|---|---|---|
| Manh phái sơ cấp lý pháp | 292 trang; 286.986 ký tự | Pilot trước: Khách–Chủ, Thể–Dụng, Tố Công; giữ bảng trụ/mệnh lệ |
| Manh phái cao cấp — Đoàn Kiến Nghiệp | 181 trang; 195.516 ký tự | Ứng kỳ/Tượng pháp; review tr.5 ít chữ, ảnh tr.30 |
| Tử Bình Chân Thuyên bình chú | 140 trang; 449.136 ký tự | School riêng, nguyên tác Thẩm Hiếu Chiêm/bình chú Từ Nhạc Ngô; review màu và ảnh tr.77 |
| Trích Thiên tuỷ bình chú — Nhậm Thiết Tiều | 202 trang; 583.731 ký tự | Đối chiếu cổ thư; xác nhận author layers/edition, không tự gộp quan điểm |
| Tên Sách Chưa Đặt.docx | 1.773 đoạn XML; 80 bảng; 130.687 ký tự | Bản biên soạn Manh phái có bình chú cá nhân; draft chờ metadata/source layers |
| CASE_01_TAN_KIM_1992.md | 59.481 ký tự | Hồ sơ giả định, ứng viên case/evaluation; không là nguồn sách/oracle |
| CASE_02_AT_MOC_1997.md | 62.479 ký tự | Kiểm tàng/thấu, thiếu căn, điều kiện chế Sát/tòng; giữ ngoài corpus chuẩn |

CASE Markdown là nguồn dẫn xuất: chỉ ứng viên case/evaluation, không mở rộng API
upload PDF/DOCX. CASE nhắc `validate_cases.py` nhưng repo không có file đó; các
tuyên bố "đã kiểm" trong CASE chưa được tái lập, cần đối chiếu trang PDF. Không
giả nội dung web chưa nhập là nguồn có trong kho. Thứ tự nhập và gate từng đợt:
[14 · Kế hoạch xây kho tri thức](14_ROADMAP.md#kế-hoạch-xây-kho-tri-thức-k2k4).

## Đơn vị dữ liệu và trạng thái chuẩn

`book` là tác phẩm; `book_version` là một ấn bản/tệp cụ thể; `object` là bytes; `page_revision` là text/layout bất biến; `generation` là lần xử lý với parser/chunker/model config; `corpus_release` là tập generation chatbot nhìn thấy. Đổi parser không tự tạo ấn bản sách mới. Đổi nội dung file tạo version mới. SHA256 giống hệt chỉ tái dùng object; không tự gộp hai record có metadata/rights khác nhau.

Job state: `queued → running → succeeded | partial | failed | cancelled`; `running → retry_wait → queued`; `running → waiting_review → queued`; `queued/running/retry_wait/waiting_review → cancel_requested → cancelled`. Terminal `failed/partial/cancelled` có thể retry bằng job mới liên kết `parent_job_id`, tái dùng stage outputs hợp lệ. `succeeded` là pipeline xong, không đồng nghĩa mọi tri thức đã được duyệt.

Stage state: `pending/running/succeeded/failed/skipped`; page quality: `accepted/review_required/excluded`; generation: `building/ready/published/superseded/withdrawn`. Review flags không làm job mắc kẹt ở 99%: API trả counters riêng `pages_total, processed, accepted, review_required, excluded, failed`, kèm stage hiện tại. Stage embed có counters chunks, không gọi chúng là pages.

## Các bước thực hiện

| Stage | Input → Output lưu bền | Khi lỗi / test trọng tâm |
|---|---|---|
| validate | stream → sha256, MIME detected, bytes, object | MIME giả, password PDF, zip bomb DOCX, oversize → quarantine |
| dedupe/version | object + metadata → book_version | unique sha256 giải race; cùng bytes trả duplicate_of, không tạo index trùng |
| inspect | PDF pages/DOCX structures → page plan | đo text coverage + glyph/Unicode + image areas từng trang |
| extract | native parser → page_revision raw blocks | giữ reading order, bbox, fonts/colors, tables/captions |
| OCR | only deficient pages/regions → OCR blocks | timeout/memory quota theo page; không mất layer chữ tốt |
| normalize | raw → NFC normalized + offset map | giữ raw; đ→d chỉ cho search field, không ghi đè tiếng Việt |
| structure | headings/TOC/layout → section hierarchy | split by heading, author-layer, table/case; unknown có nhãn |
| quality | blocks + metrics → review items | risk gates theo loại; mẫu vàng kiểm calibration |
| chunk | accepted spans → immutable chunks + source links | cross-page sources đầy đủ, không cắt hàng trụ dở dang |
| embed/index | chunks + model profile → vectors/lexical entries | batching, retry và dedupe cache; model mismatch bị chặn |
| extract candidates | chunks → candidate terms/rules/cases | JSON validate; chỉ draft, không thực thi |
| publish | validated generation → new active corpus release | atomic swap; giữ release cũ, chat tiếp tục |

Format/size mặc định cấu hình: PDF/DOCX, 250 MiB/file, 3.000 trang/file, 100 file/batch, tổng quota theo disk. Không upload RAR/ZIP vào ingestion sách; batch dùng nhiều tệp. DOCX giải nén trong sandbox, tổng uncompressed ≤1 GiB, không external relationships/macros/embedded executable. PDF mã hóa trả `PASSWORD_REQUIRED` (release này yêu cầu người dùng cung cấp bản đã mở khóa), không retry parser vô hạn. Partial sách cho phép publish phần accepted nhưng UI/citation luôn nêu coverage và excluded ranges; không trả lời phủ định toàn sách nếu coverage thiếu.

Đã triển khai (T011): stage `validate` (mở PDF, `PASSWORD_REQUIRED`/`PDF_CORRUPT`/`PAGE_LIMIT` là lỗi vĩnh viễn, ghi `coverage.total`) và `extract` (mỗi trang một unit). Ký tự → dòng → block theo khoảng cách dọc, cỡ chữ và màu; block lưu bbox chuẩn hóa sau rotation, font/cỡ/độ đậm/màu; `normalized_text` NFC, các block nối bằng một dòng trống và offset là codepoint. Trang được phân loại `text`/`sparse`/`mixed`/`scan`/`blank`: blank và sparse vẫn accepted, scan → `review_required` + `needs_ocr`, mixed giữ `image_boxes` cho OCR vùng; nhãn trang lấy từ page label PDF hoặc số trang in đứng riêng (chưa verified). Chạy lại cùng parser và cùng text tái dùng revision; output tính trước được gắn vào generation mới qua `attach`. Đo: Manh phái sơ cấp 292 trang qua pipeline + DB 18 s.

## OCR và kiểm tra chất lượng

Phân loại theo trang, không một nhãn scan/text cho toàn sách. Trang ít chữ nhưng hợp lệ (bìa, trắng, hình) không tự kết luận OCR lỗi. Các tín hiệu: text_area/image_area, replacement char rate, encoding anomalies, dictionary hit rate trong ngữ cảnh, reading order jumps, table alignment, confidence OCR engine nếu có. Không gộp các tín hiệu thành xác suất đúng giả.

Default review triggers: U+FFFD >0, glyph không ánh xạ >1%, trang có ảnh lớn không có caption/text, cột Can/Chi không khớp số hàng, heading bị tách, case thiếu ngày/giờ hoặc trụ không hợp lệ. Các ngưỡng là cấu hình chưa được benchmark; T014 phải hiệu chỉnh trên bộ 30–60 trang gán nhãn bằng mắt gồm text, bảng, scan, mixed. Page empty thật ghi loại `blank`, không OCR lặp vô hạn.

Đã triển khai (T012, `ingestion/ocr.py`, `ocr_stage.py`): stage `ocr` chỉ nhận trang `scan` (OCR cả trang) và trang có ảnh ≥2% diện tích (OCR vùng ảnh). Render bằng PDFium với trần 40 triệu pixel (DPI tự giảm; vượt trần ở 120 dpi → coi như timeout); Tesseract `vie+eng` (đổi qua `pipeline_profiles.config.ocr.languages`, có `chi_sim/chi_tra`) chạy subprocess có timeout 120 s, `OMP_THREAD_LIMIT=1`, giới hạn RAM/CPU, trong container không mạng. Timeout thử lại một lần ở 200 dpi rồi mới thành review. Block OCR chồng ≥50% lên block native bị bỏ; phần còn lại nối **sau** các block native trong revision mới (base = revision native), nên text và offset native không đổi; block OCR có `attributes.origin='ocr'`, `conf`, bbox chuẩn hóa. Confidence trung bình <60 → `review_required` + review item `OCR_LOW_CONFIDENCE`; timeout/thiếu engine/không nhận được chữ → giữ revision native, review item `OCR_TIMEOUT`/`OCR_UNAVAILABLE`/`OCR_EMPTY`; một trang không làm fail job.

Đối với ba sách mẫu: native extraction trước; Manh sơ cấp có đoạn tiếp nối và các hàng Can/Chi căn bằng khoảng trắng; cao cấp trang 30 cần ảnh gốc và OCR vùng hình nếu muốn searchable; Tử Bình có màu chữ phân biệt lớp bình chú, bảng và ảnh trang 77. Caption do AI suy luận giữ `origin=ai_inferred`, không thay text tác giả.

Đã triển khai (T014): `normalize.py` (NFC, bỏ zero-width/soft hyphen/BOM, NBSP→space, bản đồ offset về raw, chuyển codepoint↔UTF-16 cho UI); `layout.py` + parser `pdfium-native-4`: lượt quét toàn tài liệu (cỡ chữ thân bài, dòng lặp ở mép trang, trang mục lục) rồi gán `role` header/footer/folio/toc, heading có `level`/`heading_rule` (mẫu chương/La Mã/số, chữ in hoa, cỡ/đậm; hàng lá số không bao giờ là heading), block tách theo thụt đầu dòng, mục danh sách, tiêu đề đậm ngắn và dấu hiệu người nói; `speaker_layer` từ dấu hiệu "Nguyên văn"/"Từ chú"/"Bình chú…"/"(Lâm chú…" (kế thừa trong trang theo màu), còn lại `unknown`; hàng tứ trụ có `chart_row`. Stage `structure`: cây section từ heading (path `0001.0002`, hàm thuần dùng lại ở chunker), nhãn trang in được `printed_label_verified` khi ≥60% trang cùng độ lệch, trang lệch → `PRINTED_LABEL_MISMATCH`. Stage `quality`: review item `REPLACEMENT_CHARS`, `UNMAPPED_GLYPHS` (PUA >1%), `PILLAR_ROW_MISMATCH`, `HEADING_SPLIT`, `READING_ORDER`, và một item `SPEAKER_LAYERS_INCOMPLETE` cho sách có đánh dấu người nói nhưng còn đoạn chưa gán; ngưỡng ở `pipeline_profiles.config.quality`, `calibrate()` tính precision/recall theo nhãn. Kiểm bằng mắt 9 trang mẫu (sơ cấp 16/19/26, cao cấp 6/7/30, Tử Bình 26/28/77): text khớp ảnh; lỗi tìm được và đã sửa: Từ chú gộp vào Nguyên văn, đoạn mở đầu bằng cụm đậm bị coi là heading, tiêu đề đậm gộp vào đoạn, đoạn thụt đầu dòng bị gộp. Hiệu chỉnh ngưỡng trên 30–60 trang gán nhãn bởi người vẫn chờ chuyên gia (T025.1).

## Locator chuẩn

PDF `physical_page_number` 1-based; `printed_page_label` string nullable kèm confidence/verified. Không lấy số trang in làm array index. `bbox=[x0,y0,x1,y1]` chuẩn hóa 0..1 theo trang sau rotation, origin top-left; lưu page width/height/rotation. Text offsets là Unicode codepoint offsets `[start,end)` trong `normalized_text`, có map về raw blocks. JS phải đổi UTF-16 offsets trước khi highlight. `source_hash` phát hiện drift.

DOCX không có số trang vật lý ổn định. Giữ paragraph/table path vào XML và tạo **canonical rendered PDF** bằng LibreOffice headless đã pin font/render version trong worker. PDF này có object id/hash và page map. Citation ghi rõ “trang bản dựng”, không gọi đó là trang in gốc. Nếu render không thành công, citation theo mục/đoạn và `page_kind=docx_anchor`; chưa được giả số trang. T014 kiểm mapping text anchors sang bản dựng; thay renderer tạo generation mới.

Đã triển khai (T013, `ingestion/docx.py`, `docx_stage.py`): text lấy từ `word/document.xml` (từ chối DTD/entity), mỗi đoạn/bảng có anchor `body/p[i]`/`body/tbl[j]` (content control được mở, bảng giữ `table_cells`, heading theo style/outline). Bản dựng PDF bằng LibreOffice headless (profile tạm, timeout 240 s) trong image `app` với font cố định (DejaVu, Noto CJK), lưu thành object và gắn `rendered_object_id`. Đoạn được định vị trên bản dựng bằng so khớp chữ/số (bỏ số thứ tự tự động, dấu chấm mục lục, gạch nối mềm), giữ thứ tự tài liệu; cụm ngắn và bảng chỉ tìm trong 3 trang kế tiếp để cụm lặp ("Ví dụ nam mệnh:", lá số in lại) không kéo con trỏ đi xa. Kết quả `located`: `exact` (có bbox), `inferred` (bảng nằm giữa hai đoạn cùng trang, không bbox) hoặc false (chỉ anchor). Đo trên DOCX thật: 1.060/1.100 exact, 11 inferred, 29 chỉ anchor. Render lỗi → `docx_anchor` pages (số thứ tự nội bộ theo heading, bbox null) + review item `DOCX_RENDER_FAILED`; tỉ lệ định vị < 90% → `DOCX_LOCATE_PARTIAL`.

## Retry, resume và idempotency

Idempotency key stage: hash(book_version_id, source_sha, stage_name, parser_config_hash, input_revision_hash, chunker_version, embedding_profile khi cần). Unique constraint stage key; worker cạnh tranh dùng DB lease, heartbeat 30s, lease timeout khởi đầu 180s; job dài gia hạn, không dùng timeout này làm OCR runtime limit. Kết quả worker mất lease không được publish (fencing token). Mỗi page commit riêng, tiến độ giảm thiểu write amplification bằng heartbeat gộp.

Retry network/429/5xx tối đa 5 lần exponential jitter 2–120s và `Retry-After`. Corrupt/password/invalid format không retry tự động. OCR timeout một lần thử cấu hình giảm DPI rồi đưa review; không làm fail cả batch. Dispatcher/watchdog reconciliation mỗi phút, outbox được ack sau queue send nhưng dedupe vẫn bắt buộc khi send thành công mà ack thất bại.

Đã triển khai (T010, `backend/app/ingestion`): `queue.claim` tạo/khóa `job_stages` theo idempotency key, unit đã `succeeded` được tái dùng (job retry không làm lại), unit đang có lease sống → `UnitBusy`; mỗi claim tăng `fencing_token`. Handler tách `compute` (không ghi DB, chỉ blob content-addressed) và `persist` (ghi rows cùng transaction với `queue.complete`, kiểm token) nên worker chết ở bất kỳ ranh giới nào để lại "không có gì" hoặc "unit hoàn chỉnh". Lỗi tạm (`RetryableError`) → job `retry_wait` với `error.retry_at` jitter 2–120s, tối đa 5 lần/unit; lỗi vĩnh viễn (`UnitFailed`) → `failed` có mã. Cancel hợp tác giữa các unit. Outbox dispatcher dùng `FOR UPDATE SKIP LOCKED`, at-least-once; consumer dedupe qua `processed_events`. Watchdog mỗi phút: trả lease hết hạn về pending, đưa retry đến hạn về queued, kết thúc cancel không còn ai chạy, phát lại tín hiệu cho job queued/running im lặng (không lease sống, không event chờ) — Redis mất message chỉ làm chậm. `operation_jobs` dùng cùng mô hình lease/fencing. Worker: `celery -A backend.app.ingestion.celery_worker:celery worker -Q ingestion -c 1` (Windows dev thêm `--pool=solo`); watchdog+dispatcher: `python -m backend.app.ingestion.watchdog`.

Celery acks_late/prefetch=1 giúp long jobs nhưng **không thay** DB idempotency/lease. Redis visibility timeout lớn hơn stage runtime cap; job over cap split; không giữ worker vài giờ trên một task sách. Cancel cooperative giữa pages/batches; dừng process con OCR theo timeout; chỉ xóa staging chưa tham chiếu, không xóa object gốc.

## Incremental correction/reindex/publish

Sửa OCR tạo page_revision mới với `base_revision_id` và ETag. Xác định chunk chứa page/block, các chunk overlap và section/case liền kề tới ranh giới ổn định; chỉ re-embed nội dung/hash đổi. Nếu heading thay đổi, mở rộng tới toàn section bị ảnh hưởng, có thể cả sách; API preview impact trước khi admin áp dụng. Generation mới tái sử dụng chunks không đổi qua membership. Evidence trên revision cũ giữ nguyên; candidate/approved rule phụ thuộc vùng sửa bị flag `source_changed`, không tự cập nhật nghĩa đã duyệt.

Bổ sung sách không đổi embedding profile: tạo release mới từ release active + generation sách mới. Đổi profile/dimension: xây toàn bộ cohort vector mới, validate coverage, rồi atomic active swap; rollback pointer nếu recall regression. Không xóa vector cũ khi còn run ghim nó.

Thu hồi do quyền sử dụng: đặt version withdrawn và tăng `visibility_epoch` ngay; retrieval/run/citation check epoch trước hiển thị. Đây là quyền override snapshot lịch sử. History còn metadata “nguồn đã thu hồi”, không trả nội dung bị thu hồi. Garbage collect khi không còn FK/reference và hết thời gian retention.

## Benchmark 1.000 sách

Dataset manifest ghi count/bytes/pages/native/scan/mixed/DOCX/languages; SHA và quyền sử dụng. Bốn PDF hiện có (815 trang) đều native, không đại diện scan. Mở rộng bằng tài liệu được phép và fixture tổng hợp có nhãn, không giả 100 bản clone là 100 đầu sách thật.

Đo riêng throughput pages/min theo stage, p50/p95 page latency, cold/warm OCR/model, max RSS/VRAM, IO/disk growth, embeddings/min, cost/1.000 pages, failed/review %, recovery time sau kill. Run 10 → 100 → 1.000 tài liệu; 100k và 500k trang là quy mô thử nghiệm mục tiêu, có dry-run capacity estimator. Công thức dự trù vectors ≈ pages × chunks/page × dimensions × bytes/component; cộng text, indexes, images, staging và ít nhất một backup. Không biến công thức thành đảm bảo dung lượng index thực tế.
