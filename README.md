# BAZI AI — Kho tri thức Bát Tự

Ưu tiên: **sách → trích xuất/OCR → kiểm duyệt → kho nguồn → RAG có dẫn chứng**.
Dev trên Windows, commit/push Git, Ubuntu 22.04 pull và chạy containers.
Gemma dùng container `ghcr.io/ggml-org/llama.cpp:server-cuda` đã có trên Ubuntu.

Hiện có công cụ bảo toàn nguồn, kiểm kê PDF/DOCX/Markdown, kiểm tra môi trường,
tests và PostgreSQL/Redis Compose. **Chưa có web app, OCR worker, index RAG hay
kết nối Gemma hoạt động.** Xem [roadmap](docs/14_IMPLEMENTATION_ROADMAP.md),
[kế hoạch từ sách thật](docs/07_RAG_ENGINE.md) và [báo cáo T057](reports/tasks/T057.md).

## Cấu trúc

| Đường dẫn | Vai trò |
|---|---|
| `scripts/` | Công cụ vận hành, preflight sách, kiểm nguồn/secrets |
| `infra/` | Image Linux và Compose cho thành phần đã chạy được |
| `inputs/books/` | Sách gốc local, không Git; chép riêng sang Ubuntu |
| `inputs/source/`, `legacy/bazi/` | Archive/mã BaZi gốc bảo toàn, tái dùng khi làm lá số |
| `tests/` | Unit, integration, bảo mật đầu vào và regression |
| `docs/`, `TASKS.md` | Contracts, ADR và thứ tự triển khai hiện hành |
| `reports/tasks/`, `evidence/` | Báo cáo task và bằng chứng lịch sử phải giữ |
| `.tools/`, `.cache/`, `.artifacts/`, `.venv/` | Công cụ/cache/output local đã ignore |

Không tạo module rỗng. `backend/` và frontend sẽ xuất hiện cùng chức năng thật.
Scaffold Next.js/proxy/worker trỏ tới code chưa có đã bỏ ở T057; stack dài hạn
vẫn là FastAPI + Next.js + PostgreSQL/pgvector + Celery.

## Dev Windows

Cần Git và uv; uv dùng Python 3.12 theo lock. WSL/Docker không bắt buộc cho sửa
code, kiểm kê và unit tests. Docker cần khi kiểm thử containers.

```powershell
uv sync --locked --group corpus
uv run --locked --group corpus python scripts/dev doctor --target dev
uv run --locked --group corpus python scripts/dev inspect-books
uv run --locked --group corpus python -B -m unittest discover -s tests -v
uv run --locked python scripts/scan_secrets.py
```

Inspector chỉ đọc, xuất JSON SHA256/trang/đoạn/bảng/cờ xem lại; không OCR/publish.
Lưu output local vào `.artifacts/` nếu cần, không Git. `--sample-chars 1000` bật
trích đoạn local; mặc định không xuất text sách. Terminal Windows cũ có thể đặt
`$env:PYTHONIOENCODING='utf-8'`. T001 dùng `python scripts/verify_inputs.py --check`
với UnRAR trong PATH để kiểm archive/ba PDF audit/legacy. RAR5 integration cần
WinRAR trên Windows; không nhầm test skip là đã kiểm. Không chạy venv trong RAR.

## Ubuntu 22.04

Cài Docker Engine và Compose plugin theo [hướng dẫn chính thức](https://docs.docker.com/engine/install/ubuntu/).
Clone vào filesystem Linux. Không chép `.venv`, secrets, DB hoặc model qua Git.

```bash
git clone https://github.com/nguyentiendat-fenrir/bazi_ai.git
cd bazi_ai
cp .env.example .env
# Điền POSTGRES_PASSWORD; BOOKS_DIR là đường dẫn tuyệt đối tới sách trên Ubuntu.
# Chép sách riêng bằng scp/rsync, giữ nguyên bytes/tên, không git add -f inputs.
docker compose --env-file .env -f infra/compose.yaml config --quiet
docker compose --env-file .env -f infra/compose.yaml build corpus-inspect
docker compose --env-file .env -f infra/compose.yaml run --rm --no-deps corpus-inspect
docker compose --env-file .env -f infra/compose.yaml up -d --wait postgres redis
python3 scripts/dev doctor --target deploy
```

Python hệ thống Ubuntu chỉ chạy doctor; image dùng Python 3.12. Inspector không
mạng, mount sách read-only, không cần DB. Compose vẫn cần POSTGRES_PASSWORD để
resolve cấu hình. DB/Redis không publish cổng host. Doctor pass chỉ là preflight.

Cập nhật: Windows chạy tests, xem diff, stage đúng file, commit, `git push origin main`.
Ubuntu chạy `git pull --ff-only`, build lại image và kiểm kê lại. Khi backend có
migrations mới bổ sung backup/migrate/restart có kiểm thử. Không `reset --hard`,
không `compose down -v`; giữ volume `bazi-ai_*` qua các lần pull.

Gemma dùng `LLM_PROVIDER=openai_compatible`. Cấu hình `LLM_BASE_URL` kết thúc `/v1`,
`LLM_MODEL` theo model ID/alias thực và key nếu có trong `.env` trên Ubuntu.
Chưa biết URL/model/VRAM nên để trống, không khởi Gemma thứ hai. Embedding dùng
model/profile riêng. Xem [kết nối llama.cpp](docs/12_SECURITY_OPERATIONS.md).
