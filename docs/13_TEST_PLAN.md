# 13 · Test plan và release gates

## Trạng thái tài liệu

Kế hoạch này là tests **phải xây và chạy trong triển khai**. Bằng chứng audit đã chạy nằm ở [02](02_SOURCE_CODE_AUDIT.md) và `evidence/`: 9 observation tests legacy, PDF metrics, package checks. Không đánh dấu các test ứng dụng dưới đây đã pass. Chạy suite hiện có bằng `python -B -m unittest discover -s tests -v`; các module mới bổ sung kiểm thử tương ứng khi triển khai.

## Tầng kiểm thử

| Tầng | Fixture / phép thử | Gate |
|---|---|---|
| Unit | time normalize, Unicode offsets, splitter, RRF, AST types/tri-valued, permissions | Deterministic + cases biên pass |
| Integration | PostgreSQL thật, pgvector, Redis/Celery, object volume; fault injection | duplicate delivery/kill/restart không nhân bản hoặc mất published data |
| API/contract | OpenAPI snapshots, generated TS client, malformed input và scopes | statuses/DTO/security nhất quán |
| Frontend E2E | Playwright qua gateway, real backend+DB, fixture provider (`cd frontend && npx playwright test`, cần `BAZI_TEST_DATABASE_URL`) | flows empty/loaded/error/cancel/reconnect/forbidden |
| Ingestion | native/scan/mixed/malformed/encrypted PDF, DOCX table | source mapping đúng; một file lỗi không chặn batch |
| Retrieval | gold query→graded spans, scoped release | các ngưỡng ở [07](07_RAG_ENGINE.md#benchmark-retrievalanswer), không leak school/ACL |
| Citation | exists/hash/page/offset/speaker + human support | 100% ID/page validity, material support ≥95% |
| Calculation | independent oracle + policy matrix | core fixtures không mismatch chưa giải thích |
| Rule | safe AST, exception, unknown, DAG, revoke/conflict | trace và output deterministic; no code execution |
| Security | malicious doc/prompt, IDOR, CSRF, secret logs, delete canary | zero critical/high unresolved |
| Performance | 10/100/1.000 books, 100k/500k pages profile, cold/warm | đo và công bố resource/throughput; không fabricated SLA |
| Operations | backup clean-volume restore, missing blob/key, migration fail (`tests/integration/test_backup.py` chạy trong image test vì cần pg_dump 17; trên Windows bị skip, không tính là pass) | checksums+source+search+chart+chat restored |

## Calculation matrix cụ thể

CAL01: synthetic 2000-06-15 05:30, Asia/Ho_Chi_Minh, host TZ UTC/Việt/New York; canonical instant và bốn trụ identical. Assert không lấy golden legacy buggy output.

CAL02: unknown timezone, malformed offset in local_datetime, invalid dates/longitude, sex unspecified. Expected typed 422 hoặc partial documented; không fallback UTC/female.

CAL03: 12 tiết mỗi năm đại diện 1900/1945/1975/2000/2024/2100, oracle UTC instants và ±1s/±1m/±1h; UTC+7/+8 cùng physical instant có year/month giống nhau. Tolerance oracle phút không dùng làm expected chính xác đến giây; cases trong uncertainty window flagged, không fake precision.

CAL04: 22:59:59,23:00,23:59:59,00:00,00:01 cả 2 day policies; kiểm day+hour stem phối hợp theo expert-approved convention, không chỉ day.

CAL05: DST gap/fold theo IANA zone có lịch sử, ví dụ America/New_York; gap reject, fold 0/1 thành instants khác. VN historical offset fixtures phải lấy từ tzdata version ghi rõ và nguồn đối chiếu, không giả mọi năm UTC+7.

CAL06: EOT sign/season/leap year, longitudes 105/120/−180/+180; compare independent astronomy reference trong tolerance được duyệt; kiểm day rollover khi solar correction qua nửa đêm; không double offset.

CAL07: âm lịch tháng nhuận trong supported calendar; ngày không tồn tại reject; Gregorian↔lunar roundtrip; Vietnamese calendar unsupported trả code rõ nếu chưa có adapter oracle.

CAL08: 100 combinations ten-gods, 60 Na Yin pairs, hidden stems 12 branches, 120 growth states; oracle tables kiểm chuyên môn, no circular self-generated expected.

CAL09: male/female×yin/yang direction, cả 2 yun methods, trước/sau tiết; 10 vận đúng sequence/interval, unknown gender partial; không count-only.

CAL10: Lưu Niên trước Lập Xuân, giữa năm, interval cuối/đầu, tuổi thực/tuổi mụ. CAL11 Cung Mệnh/Thai Nguyên conventions+sources. CAL12 uncertainty range splitting/min/max supported dates; any near-boundary result lưu warnings và policy hash.

## Seed retrieval gold (bản nháp có locator đã kiểm tra)

Các câu sau được người soạn thiết kế đối chiếu trang trong mẫu; cần chuyên gia gán đầy đủ spans, đáp án chấm điểm và exceptions tại T025. Không coi 12 seed là bộ benchmark 60 câu đã hoàn thành.

| ID | Câu hỏi | Nguồn kỳ vọng / tiêu chí |
|---|---|---|
| G01 | Khách–Chủ được giải thích ở những cấp độ nào? | Sơ cấp PDF 16–18; trả nhiều cấp, không một mapping cứng |
| G02 | Thể–Dụng Manh Phái có đồng nghĩa Dụng Thần không? | Sơ cấp 18–20, Tử Bình 26; phân scope, không gộp |
| G03 | Vì sao tìm tố công xét can ngày rồi chi ngày? | Sơ cấp 26–27; giữ trình tự/điều kiện |
| G04 | Công thần và phế thần trong sơ cấp là gì? | Sơ cấp 20–22; kiểm exact spans trước gold approval |
| G05 | “khach chu”, “khách–chủ” có trả đúng cùng khái niệm? | Sơ cấp 16–18; đánh giá no-accent không lẫn chủ khí |
| G06 | Nguyên cục, đại vận và lưu niên khác vai trò ra sao theo cao cấp? | Cao cấp 6–7; không lấy từ trường phái khác |
| G07 | Ba phương thức ứng kỳ được nêu thế nào? | Cao cấp 7; ghi rõ tên nguồn |
| G08 | Trang có thiên văn đồ 12 địa chi ở đâu? | Cao cấp 30; viewer mở đúng ảnh, không chỉ text caption |
| G09 | Chương Luận Dụng Thần bắt đầu ở đâu? | Tử Bình 26; phân Nguyên văn/Từ chú |
| G10 | Nguyên văn và bình chú có cùng một tác giả không? | Tử Bình 2,5,26; không gộp speaker |
| G11 | Sách nêu chính xác ngày mua cổ phiếu nào để chắc chắn lãi? | No-answer; không bịa, không dẫn mệnh lệ tài vận như lời khuyên giao dịch |
| G12 | Chỉ dùng Tử Bình để định nghĩa “Tố Công” theo Manh Phái | Restrictive scope: insufficient_evidence; không lén mở rộng sang sơ cấp |

Gold thêm các bản dịch Hán Việt, bảng trụ, ngoại lệ ở trang kế, no-answer và contradictory speaker. Label độc lập với output hệ thống. Store manifest SHA/books versions, manual annotations, reviewer và split; không tune thresholds trên test split. Đánh giá retrieval riêng với generation để biết lỗi ở bước nào.

## Tám kịch bản nghiệm thu cuối

### E2E-01 · Hệ thống trống

Precondition volumes sạch, mock/live model tắt, không PDF. Steps: doctor→build→migrate→bootstrap-admin→up; login; tạo profile Gregorian synthetic, chart, mở library/chat/settings. Assert: chart đủ facts theo golden verified; DB books/chunks/rules approved=0; search empty_corpus; chat không có citation hay source claim bịa; no-key trạng thái rõ; các screen không 500. Evidence: Playwright video/screens, DB counts, request logs redacted và chart hash. Gate: unit/contract tests pass trên Windows dev; full stack pass trên Ubuntu 22.04.

### E2E-02 · Nhập ba PDF

Ba PDF audit (613 trang) là fixture cố định của kịch bản này; corpus đầy đủ hiện có (4 PDF/815 trang + DOCX, xem [05](05_DOCUMENT_PIPELINE.md#corpus-hiện-tại)) được đo riêng ở pilot. Precondition hashes khớp audit, quyền local processing cho phép, một embedding profile active. Upload cùng batch, theo dõi mọi stage; review nếu quality flagged, publish accepted content. Assert counts pages 292+181+140=613; trang gần trắng/ảnh xử lý đúng; không đòi sửa code theo filename; page mappings 9 trang visual sample chính xác; native text preserved; AI rules đều draft đến khi reviewer duyệt. Retry cùng files/key không duplicate objects/chunks vectors trong cùng generation.

### E2E-03 · Hỏi đáp có nguồn

Dùng G01/G02/G03/G09 + query không dấu; answer supported, đúng school và speaker, click citation mở đúng physical page. Thử invalid evidence ID từ fixture provider → validator chặn; simulate source withdraw giữa generation → không lộ excerpt. Evidence: retrieval hit trace, validated claims, page screenshot và gold scoring. Không chỉ kiểm “có chuỗi tên sách”.

### E2E-04 · Luận giải lá số

Chart oracle-approved + ruleset gồm ≥3 rules reviewed từ tài liệu (positive/negative/unknown fixtures), chọn Manh Phái, gọi analysis. Assert facts giữ nguyên hash; fired rules trace điều kiện/ngoại lệ/sources; unsupported interpretation ghi nhãn; switch Tử Bình tạo trace riêng. Draft/revoked rule không chạy. Nếu chưa chuyên gia duyệt rule thật, đánh dấu gate BLOCKED, fixture synthetic không thay nghiệm thu chuyên môn.

### E2E-05 · Bổ sung 100 tài liệu

Manifest ≥100 tệp nội dung khác nhau hợp pháp, mix native/scanned/DOCX và một duplicate. Upload batch không deploy/change code, giữa lúc chat query release cũ. Assert từng file có trạng thái, published docs searchable sau swap, chat cũ sources còn mở, duplicate report đúng, no OOM/corruption. Run scale 1.000 docs capacity benchmark riêng; 100 fixtures tổng hợp phải ghi là tổng hợp, không báo đã xử lý 1.000 sách thật.

### E2E-06 · Lỗi và hồi phục

Corrupt PDF, encrypted PDF, scan unreadable, timeout OCR, kill worker sau object write trước DB commit, Redis restart, duplicate queue message và disk-low. Assert healthy files tiếp tục, corrupt không retry vô hạn, watchdog resume checkpoints, fencing token chặn stale worker, staging GC không xóa published blobs, retry không tăng duplicate row count. Giữ DB invariant report trước/sau.

### E2E-07 · Cập nhật tri thức

Sửa một OCR block có citation cũ; sửa alias và tạo rule revision khác kết quả. Assert diff generation chỉ affected chunks+neighbors; old citation vẫn trỏ old revision; active snapshot không có text/vector mismatch; analysis_dependencies tìm đúng impacted analyses; re-evaluate tạo bản mới và diff, không rewrite old answer. Rule revoke khiến active ruleset loại rule đó; two concurrent reviewers → một người 412/409, không overwrite.

### E2E-08 · Backup/restore

Chuẩn bị 3 books + 1 chart + 1 hội thoại có citation + 1 draft/approved rule + 1 queued job. Backup manifest/checksum/encryption; restore vào volumes sạch, dùng pinned app version. Assert count/hash integrity, source opens, gold search result, chart hash, rule trace và conversation citation giống trước; queued job resume idempotent. Negative cases missing blob/wrong key/corrupt dump → preflight fails, không chuyển hệ thống đang chạy. Đo RTO/RPO thực, ghi deletion ledger replay test.

## Security và performance gates

SEC01 IDOR cho chart/source/evidence/run/SSE; SEC02 CSRF/login abuse; SEC03 parser zip/pixel bomb/timeout; SEC04 doc prompt injection + arbitrary tool path; SEC05 log/ZIP/secrets scan; SEC06 deletion cache/vector canary; SEC07 provider budget race. Không unresolved critical/high; mức thấp có issue owner+deadline.

PERF01 đo empty/startup; PERF02 ingest 10/100/1.000 manifest; PERF03 query 10/100 concurrent requests synthetic, không mặc định PC phục vụ được số đó; PERF04 job recovery và disk cap; PERF05 vector filter recall. Ghi CPU/RAM/VRAM/disk/model versions, warmup và 3 repeats. Số liệu synthetic load không là user SLA. Ngưỡng latency cuối chốt sau T051, nhưng không được hạ integrity/accuracy gates để đạt tốc độ.

## Release Definition of Done

Các chức năng trong phạm vi release đã được kiểm thử, không blocked calculation oracle/rights xử lý external được dùng, E2E-01…08 pass, retrieval gold đạt gate, specialist review signed, no secrets/data leak, restore drill pass, runbook Windows dev → Ubuntu thực chạy, versions locked, code+docs trong git. Nếu gate chưa đạt, ghi trạng thái **release candidate chưa nghiệm thu**, không gọi phần mềm hoàn chỉnh.
