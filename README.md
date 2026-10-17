# BAZI AI — Kho tri thức Bát Tự

Ưu tiên: **sách → trích xuất/OCR → kiểm duyệt → kho nguồn → RAG có dẫn chứng**.
Dev trên Windows, commit/push Git, Ubuntu 22.04 pull và chạy containers.
Gemma dùng container `ghcr.io/ggml-org/llama.cpp:server-cuda` đã có trên Ubuntu.

Hiện có backend kho tri thức (upload, trích xuất native/OCR/DOCX, duyệt nguồn,
chunk/embed, publish release, tra cứu hybrid có citation, adapter LLM) và web app
quản trị kho bước đầu (`frontend/`). **Chưa có lá số, chat hay Gemma thật đã smoke.** Lộ trình và trạng thái task: [docs/14_ROADMAP.md](docs/14_ROADMAP.md);
mục lục tài liệu: [docs/README.md](docs/README.md).

## Cấu trúc

| Đường dẫn | Vai trò |
|---|---|
| `scripts/` | Công cụ vận hành, preflight sách, kiểm nguồn/secrets |
| `infra/` | Image Linux và Compose cho thành phần đã chạy được |
| `inputs/books/` | Sách gốc local, không Git; chép riêng sang Ubuntu |
| `inputs/source/`, `legacy/bazi/` | Archive/mã BaZi gốc bảo toàn, tái dùng khi làm lá số |
| `backend/` | FastAPI backend (`backend/app`) |
| `frontend/` | Next.js UI; kiểu API sinh từ `contracts/openapi.json` |
| `tests/` | Unit, integration, bảo mật đầu vào và regression |
| `docs/` | Đặc tả, API/schema, lộ trình và ADR — bắt đầu từ [docs/README.md](docs/README.md) |
| `evidence/` | Manifest và audit dùng để kiểm chứng nguồn |
| `.tools/`, `.cache/`, `.artifacts/`, `.venv/` | Công cụ/cache/output local đã ignore |

Không tạo module rỗng hay màn hình placeholder: UI chỉ có màn hình mà API đã hỗ trợ.
Stack: FastAPI + Next.js + PostgreSQL/pgvector + Celery.

## Dev Windows

Cần Git và uv; uv dùng Python 3.12 theo lock. WSL/Docker không bắt buộc cho sửa
code, kiểm kê và unit tests. Docker cần khi kiểm thử containers.

```powershell
uv sync --locked --group corpus
uv run --locked --group corpus python scripts/dev doctor --target dev
uv run --locked --group corpus python scripts/dev inspect-books
uv run --locked --group corpus python -B -m unittest discover -s tests -v
uv run --locked python scripts/scan_secrets.py
uv run --locked python -m uvicorn backend.app.main:create_app --factory --port 8000
```

Migrations và integration tests cần PostgreSQL; bản dev mở cổng loopback 55432:

```powershell
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.dev.yaml up -d --wait postgres
$env:POSTGRES_HOST='127.0.0.1'; $env:POSTGRES_PORT='55432'
uv run --locked alembic -c backend/alembic.ini upgrade head
# Test tự tạo/xóa database bazi_test_*, không đụng database bazi:
$env:BAZI_TEST_DATABASE_URL='host=127.0.0.1 port=55432 dbname=postgres user=bazi password=<POSTGRES_PASSWORD>'
uv run --locked python -B -m unittest discover -s tests -v
```

Không đặt `BAZI_TEST_DATABASE_URL` thì schema tests được skip, không tính là đã kiểm.
Test cần Tesseract (OCR) chạy trong image Linux, dùng Postgres qua mạng Compose:

```bash
docker build -f infra/backend.Dockerfile --target test -t bazi-ai-test:local .
docker run --rm --network bazi-ai_internal   -e BAZI_TEST_DATABASE_URL="host=postgres port=5432 dbname=postgres user=bazi password=<POSTGRES_PASSWORD>"   -v "$PWD/inputs/books:/app/inputs/books:ro" bazi-ai-test:local   python -B -m unittest tests.integration.test_ocr -v
```

Tài khoản: không có đăng ký công khai. Sau migrate, tạo login DB cho API (thành viên
`bazi_runtime`, chịu RLS) rồi tạo admin đầu tiên; mật khẩu lấy từ prompt hoặc biến
môi trường, không qua tham số dòng lệnh:

```powershell
uv run --locked python -m backend.app.cli create-runtime-login   # đọc POSTGRES_APP_USER/PASSWORD
uv run --locked python -m backend.app.cli bootstrap-admin --email admin@example.test
```

API kết nối bằng `POSTGRES_APP_USER`. Nếu để trống, dev dùng owner và
`/health/ready` báo `RLS_BYPASS_ROLE` (degraded); production từ chối khởi động.
API đọc `.env`; config sai thì dừng ngay với tên field, không in giá trị. Kiểm
`http://127.0.0.1:8000/api/v1/health/live` và `/health/ready` (model chưa cấu hình
là `degraded`). Log là JSON một dòng, có `request_id` trùng header `X-Request-ID`.

Giao diện web (Node 22.18+; cài một lần `cd frontend; npm ci --ignore-scripts`):

```powershell
cd frontend
$env:NEXT_TELEMETRY_DISABLED='1'
npm run dev            # http://127.0.0.1:3000, /api chuyển tới API cổng 8000 (BAZI_API_ORIGIN)
npm run typecheck; npm test; npm run api:check   # api:gen sau khi export-openapi
npx playwright test    # E2E trên stack tạm, cần BAZI_TEST_DATABASE_URL như integration tests
```

Inspector chỉ đọc, xuất JSON SHA256/trang/đoạn/bảng/cờ xem lại; không OCR/publish.
Lưu output local vào `.artifacts/` nếu cần, không Git. `--sample-chars 1000` bật
trích đoạn local; mặc định không xuất text sách. Terminal Windows cũ có thể đặt
`$env:PYTHONIOENCODING='utf-8'`. Dùng `python scripts/verify_inputs.py --check`
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

Ứng dụng đầy đủ (API, worker, watchdog, UI qua gateway `127.0.0.1:${GATEWAY_PORT:-3000}`)
sau khi đã migrate, tạo runtime login và admin:
`docker compose --env-file .env -f infra/compose.yaml --profile app up -d --build`.

Gemma dùng `LLM_PROVIDER=openai_compatible`. Cấu hình `LLM_BASE_URL` kết thúc `/v1`,
`LLM_MODEL` theo model ID/alias thực và key nếu có trong `.env` trên Ubuntu.
Chưa biết URL/model/VRAM nên để trống, không khởi Gemma thứ hai. Embedding dùng
model/profile riêng. Xem [kết nối llama.cpp](docs/12_SECURITY_OPERATIONS.md#kết-nối-gemma-llamacpp).
