# 11 · Frontend UX và mapping API

## Thứ tự form quản trị kho

Theo [14](14_ROADMAP.md), UI đầu tiên phục vụ kho tri thức, theo thứ tự:

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

Đã triển khai (T043.1, `frontend/`): Next.js 16 App Router + React 19 + TypeScript strict, màn hình là client components gọi API cùng origin (dev/E2E: Next rewrite `/api/*` tới FastAPI; container: Caddy gateway). Kiểu API sinh bằng `openapi-typescript` từ `contracts/openapi.json` vào `src/api/schema.d.ts` (`npm run api:gen`; `npm run api:check` báo lỗi khi snapshot đổi mà chưa sinh lại), gọi qua `openapi-fetch`; lỗi Problem Details thành `ApiError` (code, field_errors, request_id, ETag, Retry-After) với thông báo tiếng Việt theo code. Đăng nhập lưu CSRF token của response login trong localStorage (server chỉ giữ hash; cookie phiên vẫn HttpOnly) và gửi `X-CSRF-Token` cho mọi mutation; 401 hoặc `CSRF_FAILED` ở bất kỳ màn hình nào đưa về `/login?next=` (chỉ nhận path cùng origin) kèm lý do. Shell: sidebar 240px thu gọn được (nhớ trong trình duyệt), topbar trạng thái API (admin xem `/health/ready` và tên check suy giảm), menu người dùng; điều hướng chỉ hiện màn hình có API và đúng quyền. Màn hình: `/login`, `/` (reviewer: jobs chạy/chờ, mục cần duyệt, release đang dùng; mọi người: sách), `/books` (tìm không dấu, cursor “Tải thêm”, cột kho tra cứu từ `active_coverage`), `/books/[id]` (thông tin + phiên bản: trạng thái, quyền, xử lý ngoài, trang đạt/tổng, kích thước, SHA-256). Mỗi màn hình có loading (skeleton không số giả), empty có hướng dẫn, error có request id + thử lại, 403/404 riêng. CSP chặn script/kết nối ngoài origin, `frame-ancestors 'none'`; text sách chỉ render dạng text.

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

Đã triển khai (T043.1): `frontend/e2e` chạy Playwright trên Edge cài sẵn (Linux: `E2E_BROWSER_CHANNEL=` + `npx playwright install chromium`), webServer khởi `scripts/e2e_stack.py` (database `bazi_e2e_*` mới trên server test, runtime login, admin/reviewer/reader, pipeline fixture, PDF tổng hợp, worker chạy job trong process, OCR tắt) và `next build && next start` với rewrite tới API đó. 11 flow: chặn chưa đăng nhập + quay lại trang yêu cầu, sai mật khẩu, reader thư viện rỗng/không thấy panel vận hành, số liệu dashboard reviewer, tìm sách không dấu + trang chi tiết, sách riêng tư → 404 với reader, đăng xuất, phiên hết hạn, API không tới được + thử lại, health admin, không tràn ngang ở 1280x720/1920x1080. Unit test logic thuần chạy `npm test` (node:test).

Đã triển khai (T046.1): `/books/upload` (một batch, pipeline profile mới nhất đã sẵn sàng được chọn sẵn hoặc “chỉ lưu tệp”, quyền/ấn bản/ngôn ngữ/cho phép xử lý ngoài áp cho mọi tệp, cảnh báo khi profile dùng mô hình bên ngoài mà tệp không cho phép; mỗi tệp một request multipart có tiến độ, hai tệp song song, Idempotency-Key riêng giữ khi lỗi mạng và đổi khi bị từ chối; lỗi từng tệp kèm mã + “Thử lại tệp này”, tệp trùng dẫn tới phiên bản đã có; `?book=` thêm phiên bản cho sách sẵn có). `/jobs` (lọc trạng thái/phiên bản, tự cập nhật 3 s khi còn job chạy) và `/jobs/[id]` (bước: phần việc/tính mới/tái dùng, lỗi vĩnh viễn hay tạm thời, nhật ký sự kiện tăng dần theo seq, hủy/thử lại có xác nhận, liên kết job con). `/versions/[id]` (thông tin phiên bản, bản dựng hiện tại với trang đạt/cần duyệt/loại trừ/thiếu và các khoảng ngoài tra cứu, trang và jobs; “Xử lý lại từ đầu”; “Publish…” chỉ khi bản dựng sẵn sàng, publish thiếu trang phải tick xác nhận đúng các khoảng trang; “Thu hồi…” phải gõ đúng tên sách + lý do). `/review` (hàng đợi mục trang, lọc trạng thái/lý do/phiên bản) và `/pages/[revisionId]` (ảnh trang có thu phóng và khung bbox của từng khối, chọn khối hai chiều; sửa text/lớp người viết, diff theo từ trước khi lưu, lý do bắt buộc; lưu với If-Match bản mới nhất; 412 → tải bản mới, áp lại thay đổi của mình theo từng khối và đánh dấu khối bị sửa khác nhau; chấp nhận/loại trừ/chạy lại OCR/bỏ qua mục duyệt có lý do, chỉ trên bản mới nhất và khi không còn thay đổi chưa lưu). Trang sách: sửa tên/ngôn ngữ/mô tả với If-Match, 412 giữ bản nháp và hiện bản người khác vừa lưu. Bảng không sửa trong UI (chỉ hiển thị ô). E2E thêm 6 flow trên stack thật: upload (một tệp sai định dạng) → job → publish → tệp trùng; trang quét đối chiếu ảnh → loại trừ → publish thiếu trang có xác nhận; sửa trang thua race 412 vẫn giữ và lưu được; sửa sách 412; job lỗi `PDF_CORRUPT` → thử lại một lần; reader không vào được upload/jobs/review (UI + API 403).

Đã triển khai (T044): `/charts` (tìm theo tên hồ sơ, trụ năm/tháng/ngày/giờ, cờ thiếu trụ), `/charts/new` (dương lịch hoặc âm lịch Việt/Trung kèm tháng nhuận, múi giờ IANA, độ chính xác giờ — không biết giờ thì không giả định 12:00, khoảng giờ cho ra biến thể; giờ không tồn tại vì DST báo ngay tại ô, giờ lặp phải chọn lần thứ nhất/thứ hai; chọn policy, giới tính để tính chiều vận; lưu thành hồ sơ tùy chọn), `/charts/[id]` (bảng Tứ Trụ với nhãn ngũ hành không chỉ bằng màu, tàng can, thập thần, trụ chưa biết ghi rõ; biến thể khi giờ không chắc; mốc thời gian UTC/giờ địa phương/giờ mặt trời, tiết khí; quan hệ can chi; đại vận và lưu niên; chi tiết tính toán; xóa có xác nhận; “Hỏi về lá số này” mở `/chat`). E2E 4 flow.

Đã triển khai (T045): `/chat` danh sách hội thoại của mình (tìm, xóa có xác nhận — câu trả lời đang chạy bị hủy), thanh ngữ cảnh (chế độ tra cứu/luận lá số/so sánh, lá số, trường phái, phương pháp đã duyệt của trường phái đã chọn) lưu bằng PATCH + If-Match; composer gửi với Idempotency-Key (Enter gửi, Shift+Enter xuống dòng); tiến độ qua SSE `/runs/{id}/events` (bước công cụ, claim đã kiểm hiện dần), “Dừng” hủy run, mở lại trang vẫn theo tiếp run đang chạy; câu trả lời chỉ hiển thị Answer đã kiểm (trạng thái, nhận định theo loại/mức hỗ trợ/trường phái, trích dẫn có trang + lớp người viết + mở trang nguồn, bất đồng, giới hạn, câu hỏi gợi ý). `?chart=` tạo hội thoại luận lá số. Chọn sách giới hạn (book_ids) để T047. E2E 3 flow (hỏi→trả lời qua SSE, ngữ cảnh giữ sau reload, mở từ lá số + xóa).

Playwright flows dùng API thật cùng fixture dataset synthetic; test state empty + loaded + provider unavailable + job failed + 412 race + forbidden citation. Kiểm 1280x720 và 1920x1080; không horizontal overflow trong chat, bảng lá số có responsive labels. Không demo-only endpoints hoặc dữ liệu hardcode ở production. Snapshot visual chỉ bổ sung, không thay assertion hành vi.
