# BAZI AI — Bộ đặc tả bàn giao Codex

**Phiên bản thiết kế 1.0 · hoàn tất 11/10/2026 · tiếng Việt.** Đây là bộ thiết kế để triển khai phần mềm đầy đủ, chưa phải ứng dụng đã xây xong. Các kiểm tra đã chạy trong phiên Work chỉ áp dụng cho đầu vào/audit và tính nhất quán tài liệu; không đồng nghĩa hệ thống tương lai đã vượt nghiệm thu.

## Bắt đầu trong VS Code trên Windows

1. Giải nén `BAZI_AI_CODEX_SPEC.zip`; mở đúng thư mục `BAZI-AI` trong VS Code. Không mở mỗi file ZIP.
2. Cài/bật WSL2, một bản Ubuntu còn hỗ trợ, Docker Desktop với WSL integration; mở thư mục bằng VS Code **WSL: Open Folder in WSL**. Đặt repository trong `~/projects/BAZI-AI`, tránh đặt data PostgreSQL trên `/mnt/c`. Chưa cần GPU, tên miền hoặc VPS.
3. Chép `bazi.rar` vào `inputs/source/bazi.rar`; chép ba PDF vào `inputs/books/` khi chạy kiểm thử tích hợp. Tài liệu đã audit các tệp đó nhưng không nhúng lại sách và môi trường `.venv` vào ZIP. Có thể xây các module khi thư mục sách rỗng.
4. Đọc `AGENTS.md`, sau đó gửi nguyên văn `CODEX_START_PROMPT.md` cho Codex. Nhiệm vụ đầu là T001; Codex phải kiểm tra trạng thái repository trước khi làm.
5. Chạy tuần tự T001–T056 theo `TASKS.md`. Mỗi task có phụ thuộc, contract, test và nghiệm thu. Không đánh dấu toàn bộ phần mềm hoàn thành sau khi chỉ có UI hay vài API.

Các lệnh dưới đây là **contract vận hành phải được Codex tạo**, chưa tồn tại trong gói đặc tả:

```bash
cp .env.example .env
# Điền mật khẩu và secrets cục bộ; không commit .env
./scripts/dev doctor
./scripts/dev build
./scripts/dev migrate
./scripts/dev bootstrap-admin
./scripts/dev up
./scripts/dev test smoke
```

`doctor` phải kiểm tra Docker Compose, WSL, RAM/disk trống, cổng 3000, biến môi trường, quyền volume và khả năng tải dependencies. Không tự xóa môi trường WSL cũ. Thành phẩm mở ở `http://localhost:3000`; chỉ bind cổng này vào `127.0.0.1`. Local chart và quản trị hoạt động không có LLM key. Khi chưa cấu hình model, chat báo rõ và không giả vờ đang gọi AI.

## Danh mục tài liệu

| File | Nội dung có thẩm quyền |
|---|---|
| `AGENTS.md` | Quy tắc Codex, thay đổi contract, Definition of Done |
| `TASKS.md` | 56 nhiệm vụ triển khai, phụ thuộc và checklist |
| `CODEX_START_PROMPT.md` | Prompt bắt đầu/tiếp tục triển khai |
| `docs/01_MASTER_SPEC.md` | Phạm vi, invariants, yêu cầu và nghiệm thu |
| `docs/02_SOURCE_CODE_AUDIT.md` | Audit mã/PDF, kết quả thực chạy và giới hạn |
| `docs/03_ARCHITECTURE.md` | Module boundaries, runtime, luồng giao dịch |
| `docs/04_DATABASE_SCHEMA.md` | Bảng, kiểu dữ liệu, khóa, index và migrations |
| `docs/05_DOCUMENT_PIPELINE.md` | Nhập sách, OCR, chunk, job, version, publish |
| `docs/06_KNOWLEDGE_MODEL.md` | Thuật ngữ/trường phái/quy tắc/mệnh lệ và duyệt |
| `docs/07_RAG_ENGINE.md` | Tìm kiếm hybrid, tiếng Việt, nguồn và benchmark |
| `docs/08_BAZI_ENGINE.md` | Calculation contract, lịch và Rule DSL |
| `docs/09_AI_REASONING.md` | Ba chế độ chat, tools, claims và streaming |
| `docs/10_API_SPEC.md` | REST, DTO, lỗi, quyền và SSE |
| `docs/11_FRONTEND_UX.md` | Màn hình, luồng thao tác, trạng thái và accessibility |
| `docs/12_SECURITY_OPERATIONS.md` | Secrets, quyền, vận hành, backup/restore |
| `docs/13_TEST_PLAN.md` | Test matrix, 8 kịch bản cuối, release gates |
| `docs/14_IMPLEMENTATION_ROADMAP.md` | Thứ tự triển khai, milestone và xử lý blocker |
| `docs/15_ARCHITECTURE_DECISIONS.md` | ADR, thông số cần benchmark, nguồn kỹ thuật |

`evidence/` có 2 script audit tái lập và các manifest/kết quả kiểm tra, không phải mã ứng dụng. `evidence/` chứa số liệu kiểm tra đầu vào, kết quả probe, mã probe tái lập và báo cáo kiểm tra gói. Không chứa sách, thông tin đăng nhập hoặc hồ sơ sinh người dùng. Ngày sinh trong probe là dữ liệu tổng hợp phục vụ kiểm tra.

## Những quyết định cốt lõi

- Modular monolith: Next.js/TypeScript, FastAPI/Python, PostgreSQL + pgvector, Redis/Celery. Worker là process chạy cùng codebase, không phải microservice nghiệp vụ.
- Tái sử dụng `backend/bazi.py` qua adapter sau các sửa lỗi được kiểm thử. Không dùng kết quả LLM để tính Tứ Trụ.
- Local filesystem object store có giao diện S3 adapter, thay vì bắt buộc MinIO Community đã bị archive. S3 adapter và kiểm thử của nó vẫn thuộc phạm vi bàn giao.
- Document store và structured knowledge là hai lớp riêng. Chỉ quy tắc đã duyệt được thực thi. Trường phái và lớp tác giả/bình chú được lưu rõ.
- Mọi câu trả lời ghim phiên bản lá số, rule set và nguồn; cập nhật sách không làm mất nguồn của hội thoại cũ.

## Những điểm chưa thể coi là đã kiểm chứng

Chưa có bộ oracle chuyên môn độc lập cho toàn bộ lịch/Đại Vận/Cung Mệnh; chưa benchmark model hoặc 1.000 sách; chưa chạy ứng dụng FastAPI/Next.js/Docker hoàn chỉnh; chưa xác minh quyền khai thác thương mại sách. Các việc này có task và release gate rõ ràng, không bị đẩy ra ngoài phạm vi.

## Kiểm tra đầu vào T001

Đã có công cụ `python scripts/verify_inputs.py --check`: đối chiếu input và legacy
với docs/02 cùng evidence; chỉ đọc, xuất JSON ra stdout, exit 1 khi bị chặn.
`--extract` chỉ bảo toàn source đã xác thực vào `legacy/bazi/`, không chạy script
trong archive và không ghi đè cây legacy có sẵn. Lưu JSON stdout vào báo cáo để giữ
manifest kiểm kê; không chỉnh các manifest audit gốc.

Đọc RAR cần môi trường công cụ riêng với `scripts/requirements-t001.txt` và UnRAR
cài trên máy, có trong PATH. Không dùng `.venv` trong RAR. Trên máy hiện tại:

```powershell
python -m venv .tools/t001
./.tools/t001/Scripts/python.exe -m pip install -r scripts/requirements-t001.txt
$env:PATH = 'C:\Program Files\WinRAR;' + $env:PATH
./.tools/t001/Scripts/python.exe scripts/verify_inputs.py --check
# Chỉ chạy sau khi đủ input và đã giải quyết chênh lệch đặc tả:
./.tools/t001/Scripts/python.exe scripts/verify_inputs.py --extract
./.tools/t001/Scripts/python.exe -B -m unittest discover -s tests -v
python scripts/scan_secrets.py
```

Trạng thái và giới hạn thực tế nằm ở [báo cáo T001](reports/tasks/T001.md), các
blocker ở [issues T001](reports/tasks/T001/issues.md). T001 chưa được nghiệm thu;
chưa triển khai T002. Lệnh `scripts/dev` phía trên vẫn là contract cho các task sau.
