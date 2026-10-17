# Tiếp tục phát triển BAZI-AI

1. Đọc AGENTS, README, TASKS, docs/14 và ADR-21 ở docs/15; kiểm git status/diff,
   reports và code hiện có. Đọc schema/API contract trước khi đổi module liên quan.
2. Ưu tiên kho tri thức: nguồn → native/OCR → review → chunk/index → citations.
   Dev Windows native; runtime Ubuntu 22.04 cùng host với Gemma llama.cpp có sẵn.
3. T001 đã pass; không làm lại/sửa nguồn gốc. T002 cần nghiệm thu Ubuntu thật;
   T057 là cấu trúc/preflight/roadmap, không full app. Không ép WSL máy dev.
4. Theo subtask/dependencies hiện hành trong TASKS/docs/14, đưa library trước
   chart/chat. Không tự chạy nhiều agent hoặc migrations song song.
5. Tạo chức năng cùng tests, chạy thực, cập nhật một reports/tasks/Txxx.md và
   commit đúng scope. Không gọi mock là đã OCR, kết nối Gemma hoặc đạt benchmark.
6. Không commit sách/secrets/output OCR/DB/models/cache; không xóa legacy,
   migrations, approved specs hoặc evidence. Thay contract phải có ADR diff.
