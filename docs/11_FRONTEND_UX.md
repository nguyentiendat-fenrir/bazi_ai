# 11 · Frontend UX và mapping API

## Thứ tự form quản trị kho

Chưa có frontend ứng dụng. Theo [14](14_ROADMAP.md), UI đầu tiên phục vụ kho tri thức,
theo thứ tự:

1. Nhập sách: file, nhan đề, tác giả/bình chú/dịch giả, edition, school, language,
   rights; checksum/dedupe, unknown metadata, mặc định không tự publish.
2. Jobs: native/OCR theo trang, stage/counters, retry/cancel từng job.
3. Duyệt nguồn: ảnh/text cạnh nhau, bảng Can/Chi, author layers, diff/reason,
   affected chunks và conflict 412.
4. Publish: coverage/excluded pages, model profile, release readiness và quyền.
5. Search/evaluation: query + scope sách/school, evidence mở đúng trang;
   lexical-only/degraded rõ ràng và gold đã duyệt.

Subtask T043.1 (shell/library navigation) và T046.1 (library/jobs/review) đi trước
chart/chat; T043/T046 chỉ done khi đủ integration đầy đủ. Giữ route/DTO bên dưới,
không dựng màn hình placeholder khi API chưa có.

## Bố cục thống nhất

Desktop-first 1280–1920px; vẫn dùng được 1024px và tablet landscape. Sidebar 240px thu gọn, topbar chứa trạng thái kết nối, main content max width linh hoạt. Font system sans hỗ trợ Việt, nội dung 15–16px, line-height 1.5, màu nền sáng, navy/teal làm chức năng chính; ngũ hành dùng palette cố định và nhãn chữ, không chỉ màu. Không thêm gauge/đồ thị “độ đúng vận mệnh” hoặc card trang trí không có dữ liệu.

Keyboard navigation, visible focus, labels thật, error gắn field, contrast AA, dialog trap focus, screen reader thông báo job/stream có debounce. Mỗi screen có empty/loading/error/degraded/permission-denied state và action tiếp theo. Loading skeleton không giả số liệu. Dùng generated API client và cache keys theo owner/scope/revision; không duplicate calculation ở browser.

## Màn hình và hành vi nghiệm thu

| Route UI | Công việc chính | API chính | Empty/error bắt buộc |
|---|---|---|---|
| `/` | dashboard job đang chạy, sách cần kiểm tra, lịch sử của mình | dashboard,operations/metrics theo quyền | 0 sách là 0, CTA upload/lập lá số |
| `/chat` | ba chế độ, chọn chart/school/books, history search | conversations/messages/runs/events | chưa model/chưa sách nêu rõ, composer vẫn lưu yêu cầu |
| `/charts/new` | Gregorian/lunar supported, timezone, precision, policy | calculation-policies,charts | invalid date/DST fold/unknown hour ngay tại form |
| `/charts/[id]` | bảng Tứ Trụ, tàng can/thập thần, vận, policy và trace | charts,analyses,trace | missing hour để trống có nhãn; không tô thành chắc chắn |
| `/charts` | tìm, lưu, xóa, chọn active chart | charts,birth-profiles | không có chart → tạo mới |
| `/books` | title/edition/author/school/rights/coverage filters | books,versions | không có nguồn → upload |
| `/books/upload` | chọn nhiều file, metadata, rights/external processing | ingestion-batches,uploads | lỗi từng file, retry riêng; concurrency 2 |
| `/jobs` | tiến độ file/stage/page, log, cancel/retry | jobs/events | queue unavailable không mất jobs đã ghi |
| `/review/ocr` | page image+text, bbox selection, diff corrections | review-items,page-revisions,corrections | page scan khó đọc → exclude có lý do |
| `/knowledge/terms` | concepts/aliases scoped, search, review | concepts,terms,schools,reviews | cùng label khác nghĩa hiện hai record |
| `/knowledge/rules` | school/method, source+DSL+fixtures, approve/revoke | rules,rulesets,reviews,impact | draft không có nút dùng analysis |
| `/cases` | grid bốn trụ + narrative/events/source; edit thiếu giờ | cases/revisions | không tự suy ngày sinh từ tứ trụ |
| `/evaluation` | dataset gold, runs, failed examples, comparison | evaluation-* | fixture score không gắn nhãn benchmark thật |
| `/settings` | provider profiles, budget, storage health, users, backup | settings,model-profiles,usage,operations | key không hiển thị; no provider test rõ |

## Chat interaction

Composer dưới cùng, sidebar history có search/star/delete; header chips mode/active chart/school/book filters có thể chỉnh. Thay context ghi revision, request đang chạy giữ scope cũ và hiển thị scope đó. New run không chồng cùng assistant placeholder; disable gửi trùng bằng client_message_id/idempotency.

Câu trả lời chia facts, source statements/interpretation và limitations khi cần, không ép template dài cho câu hỏi ngắn. Citation chip “Sơ cấp · tr. 16” mở source drawer có trang PDF, số trang in, tên ấn bản, speaker, đoạn highlight và nút mở trang trước/sau. Rule-derived claim có nút “Điều kiện đã kiểm tra”, hiện predicate/facts/source, không chain-of-thought LLM.

Streaming hiển thị trạng thái đang tìm/kiểm chứng rồi từng claim được duyệt; không show raw token chưa validate. Disconnect hiện reconnect; refetch run tránh gửi lại POST. Conflict hiển thị hai quan điểm cạnh nhau với method/source. Một mode so sánh tối đa 3 scopes mỗi run ban đầu để kiểm soát context, cấu hình mở rộng có benchmark.

## Form lá số và thời gian

Chọn timezone IANA bằng tên địa danh; mặc định Asia/Ho_Chi_Minh nhưng luôn hiển thị. Option giờ Mặt Trời có longitude và preview correction, không tự bật. Policy ngày 00h/23h giải thích ngắn; ngày sinh input không tự convert qua JavaScript Date UTC. Không rõ giờ có toggle “Chưa biết giờ”, không ép nhập 12h. Hiển thị timezone lịch sử/offset tính thực tế, provenance engine và cảnh báo gần ranh giới.

Bảng trụ thứ tự Năm–Tháng–Ngày–Giờ, các hàng Thập Thần/Can Chi/Tàng Can/Trường Sinh/Nạp Âm. Đại Vận theo interval, Lưu Niên hiển thị năm tiết khí và thời điểm Lập Xuân. Điểm Ngũ Hành nếu bật được ghi “thống kê theo công thức”, không label “mạnh/yếu chuẩn”.

## Review và thao tác nguy hiểm

OCR correction hiển thị base revision và affected chunks/cases/rules; save conflict 412 giữ local edits cho rebase. Rule approve phải xem sources, exceptions, fixtures; nút approve tách khỏi save draft. Revoke hỏi lý do, cho preview impacted analyses; không xóa lịch sử.

Xóa sách/hồ sơ/hội thoại và restore có confirmation nội dung cụ thể + phạm vi, không popup chung “Are you sure?”. Backup UI có lần khôi phục thử gần nhất; trạng thái “sao lưu thành công” khác “đã kiểm thử khôi phục”. Source viewer render an toàn, không active content hoặc external link tự mở.

## Frontend verification

Playwright flows dùng API thật cùng fixture dataset synthetic; test state empty + loaded + provider unavailable + job failed + 412 race + forbidden citation. Kiểm 1280x720 và 1920x1080; không horizontal overflow trong chat, bảng lá số có responsive labels. Không demo-only endpoints hoặc dữ liệu hardcode ở production. Snapshot visual chỉ bổ sung, không thay assertion hành vi.
