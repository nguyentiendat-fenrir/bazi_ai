# T001 — Theo dõi issues

Ngày kiểm tra: 11/10/2026 (Asia/Saigon). I01–I03 đã xử lý trong T001;
I04 là tình trạng môi trường để xét ở T002, không chặn nghiệm thu T001.

## T001-I01 — Archive nguồn: RESOLVED

Đã nhận `inputs/source/bazi.rar`, đo trực tiếp 35.305.832 bytes và SHA256
`9409da54f27b9eb11ee38ff7ebb09903d99c7d835a2bef8eff0d99d6c3cdd9c3`,
khớp docs/02. Công cụ bảo toàn đúng 10 source files vào `legacy/bazi/` và kiểm
tra lại từng hash. Archive gốc giữ nguyên byte sau thao tác. Bằng chứng:
`real_input_hashes.json`, `real_archive_inventory.json`, `real_preservation_check.json`.

Ba PDF mới cũng khớp toàn bộ size/hash audit; chỉ dùng làm đầu vào xác minh T001,
không đưa vào Git hoặc hardcode ứng dụng.

## T001-I02 — Sai số đếm trong audit: RESOLVED

Tái hiện: docs/02 mục 2 ghi **“9 tệp gồm .gitignore”**. Lọc
`evidence/source_manifest.json`, bỏ `dependency/` và cache/binary theo AGENTS,
còn **10** tệp: `.gitignore`, `README.md`, năm tệp `backend/`, ba tệp `frontend/`.
Bảng module của docs/02 có 9 hàng nhưng chưa liệt kê `.gitignore`.

RAR thật có 1.444 entries, tổng expanded 43.471.231 bytes. Đủ **10** source
files ngoài `dependency/` và runtime; cả 10 size/hash khớp manifest. Đã sửa
**duy nhất** số đếm “9” → “10” ở docs/02 mục 2, không sửa manifest/hash hoặc
những nhận xét audit khác. Test contract trước đây cố ý bắt chênh lệch; sau khi
có bằng chứng thật, đổi assertion thành xác nhận hai nguồn nhất quán. Test
malicious archive và mismatch tiếp tục giữ nguyên.

Đây là correction dữ kiện, không đổi schema/API/DSL, không có migration hay
rollback dữ liệu. Nếu cần hoàn nguyên văn bản, diff docs/02 chỉ một con số;
source và archive không bị tác động. Bằng chứng: `real_archive_inventory.json`.

## T001-I03 — Git metadata/commit: ĐANG CHỐT

Trước thao tác, `git status`, `git log` và `git rev-parse` đều xác nhận không có
repository/lịch sử Git. Đã `git init -b main` tại workspace. Git dùng danh tính
đã cấu hình sẵn tại user config, không đặt danh tính giả. Commit ID và kiểm tra
staging sẽ được ghi trong `T001.md` khi hoàn tất.

## T001-I04 — Môi trường ứng dụng chưa sẵn sàng (ghi nhận, ngoài phần cài đặt T001)

Python hiện có 3.13.5; baseline ứng dụng ở docs/03 là 3.12. WSL mặc định version 2
nhưng chưa có distro. Docker CLI không tìm thấy trong PATH hoặc đường cài Docker
Desktop thông thường. Không kết luận một phép kiểm tra PATH là quét mọi ổ đĩa.
Chỉ dùng venv công cụ mới `.tools/t001`, không chạy/copy venv từ archive.
Không cài Docker, distro, runtime ứng dụng hay triển khai T002 trong task này.
