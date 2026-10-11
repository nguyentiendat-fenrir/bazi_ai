# Prompt gửi cho Codex trong VS Code

Bạn đang triển khai BAZI-AI theo bộ đặc tả đã chốt trong repository này. Hãy thực hiện công việc, không chỉ trả lời kế hoạch.

1. Đọc AGENTS.md, README.md, TASKS.md, docs/01_MASTER_SPEC.md, docs/02_SOURCE_CODE_AUDIT.md, docs/03_ARCHITECTURE.md, docs/14_IMPLEMENTATION_ROADMAP.md và docs/15_ARCHITECTURE_DECISIONS.md. Đọc thêm 04/10 và contract tương ứng trước khi tạo schema/API.
2. Kiểm tra thư mục hiện tại, git status, code đã có, môi trường Windows/WSL2/Docker, tài nguyên và đầu vào. Không ghi đè công việc hiện có. Gói này là đặc tả, không giả định application code hoặc scripts vận hành đã tồn tại.
3. Nếu là lần đầu, thực hiện **T001**: lập inventory, xác thực checksum bazi.rar, giải nén an toàn bản legacy để bảo toàn; lập kế hoạch triển khai theo dependencies. Không cài/chạy `.venv` trong RAR. Nếu thiếu RAR, ghi chính xác đường dẫn cần bổ sung, đánh dấu phần bảo toàn bị chặn và tiếp tục phần setup không phụ thuộc; không tự viết lại engine.
4. Nếu đã có tiến độ, xác minh task đã đánh dấu hoàn thành bằng commit/test log và chọn task chưa hoàn thành đầu tiên có đủ dependencies. Không làm lại phần đã pass.
5. Triển khai task, chạy đúng tests, ghi reports/tasks/Txxx.md. Chỉ đánh dấu xong khi tiêu chí nghiệm thu đạt. Báo kết quả cụ thể và task tiếp theo.
6. Không tự thay stack/schema/API/chính sách tính lịch; muốn đổi contract phải đưa ADR diff cụ thể. Các việc triển khai đúng thiết kế, sửa lỗi đã xác minh và tạo test là công việc đã được ủy quyền.
7. Không bỏ ingestion, structured knowledge, Rule Engine, hybrid retrieval, citations, backup hay evaluation để thay bằng prompt LLM hoặc UI giả. Không cần sách mới để bổ sung module. Không gọi LLM có phí nếu chưa cấu hình ngân sách; có fixture/provider giả cho test.

Bắt đầu kiểm tra repository và thực hiện nhiệm vụ đầu tiên ngay.
