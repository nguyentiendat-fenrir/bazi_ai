# BAZI AI — Kho tri thức Bát Tự

Ưu tiên: **sách → trích xuất/OCR → kiểm duyệt → kho nguồn → RAG có dẫn chứng**.
Dev trên Windows, commit/push Git, Ubuntu 22.04 pull và chạy containers (LLM Qwen3-8B trên vLLM, GPU 4090).

📐 **Tài liệu kiến trúc, review code và tiến độ bàn giao (artifact):**
<https://claude.ai/artifact/HnuZ5upbo42eQ97fZ69dao>

Hiện có:
- **Kho tri thức:** upload, trích xuất native/OCR/DOCX, duyệt nguồn, chunk cha/con, embed, publish release, tra cứu hybrid có citation; web app quản trị (`frontend/`), trang chấm `/judge`.
- **Thuật ngữ đã duyệt** ([glossary_v1.json](backend/app/knowledge/data/glossary_v1.json), 1.293 khái niệm theo Tứ Trụ chung / Tử Bình / Manh phái). Mỗi nguồn là *link mềm* (mã sách + trang + câu neo) theo danh bạ [books.json](backend/app/knowledge/data/books.json); mỗi máy tự tra trong thư viện của mình, sách không vào Git.
- **Dữ kiện lá số** ([pillar_facts.py](backend/app/calc/pillar_facts.py)): đọc tứ trụ + đại vận viết trong câu hỏi, tính bằng bảng tra (thập thần, tàng can, trường sinh, Lộc/Kình Dương/Thiên Mã, hợp–xung–hình–hại, ám hợp, tự hợp; không xét hợp hóa).
- **Harness trả lời** ([answering/](backend/app/answering/)): tách ý → vòng kiểm đủ kiến thức (tối đa 7 vòng, bắt câu trích nguyên văn) → phân tích B3–B7 → tổng hợp có dẫn `[P#]`, tách Tử Bình / Manh phái.
- **MCP server của RAG** tại `/api/v1/mcp/` (bearer token) hoặc stdio: `search_books`, `answer_question`, `chart_facts`, `lookup_terms`. Xem [docs/09](docs/09_AI_REASONING.md).

Lộ trình và trạng thái task: [docs/14_ROADMAP.md](docs/14_ROADMAP.md); mục lục tài liệu: [docs/README.md](docs/README.md).

## RAG pilot: chatbot hỏi đáp từ sách và trang chấm

Pipeline gồm các bước sau:
- OCR SenOCR-Vi (GPU).
- Chunk cha/con theo chương → mục → tiểu mục, kèm metadata và tóm tắt Qwen.
- Embedding và reranker Jina (CPU).
- Trộn hybrid 0,8·dense + 0,2·BM25.
- Qwen3-8B trên máy này trả lời chỉ từ các đoạn sách được đưa vào, có trích `[P#]`.

Cấu hình Qwen nằm ở [infra/qwen.md](infra/qwen.md); quyết định và số đo ở decision log trong [docs/15](docs/15_ARCHITECTURE_DECISIONS.md#decision-log).

```bash
C="docker compose --env-file .env -f infra/compose.yaml"
$C build && $C up -d --wait postgres redis
python3 scripts/dev migrate --without-backup
# Mô hình vào volume model_cache (cần mạng; service mount volume read-only nên dùng docker run)
docker run --rm --user 0 -v bazi-ai_model_cache:/models -e HF_HUB_OFFLINE=0 bazi-ai-app:local \
    python -m backend.app.cli fetch-models
$C run --rm api python -m backend.app.cli create-runtime-login
$C run --rm -e BAZI_BOOTSTRAP_PASSWORD api python -m backend.app.cli bootstrap-admin --email admin@example.test
$C run --rm api python -m backend.app.cli rag-setup
# Mật khẩu chấm: hash vào JUDGE_PASSWORD_HASH='…' trong .env (giữ dấu nháy đơn vì hash có '$')
$C run --rm -e BAZI_JUDGE_PASSWORD api python -m backend.app.cli judge-password
$C --profile app up -d
$C run --rm -v "$PWD/inputs/books:/books:ro" worker \
    python -m backend.app.cli ingest-folder /books --admin admin@example.test
BAZI_EVAL_EMAIL=admin@example.test python3 scripts/rag_eval.py run   # 20 câu → /judge
# Thuật ngữ đã duyệt: kiểm nguồn với sách của máy này rồi nạp vào kho
python3 scripts/glossary_sources.py --books inputs/books --check
$C run --rm api python -m backend.app.cli load-glossary --as admin@example.test --publish
# Harness trả lời trên Qwen: 20 câu trong test_questions.txt, kết quả markdown + vết từng bước
$C run --rm api python -m backend.app.answering.run test_questions.txt --as admin@example.test \n    --publish harness-1     # --publish: đưa lên /judge để chấm
```

**MCP:** đặt `MCP_TOKEN` (≥ 32 ký tự) và `MCP_USER_EMAIL` (tài khoản mà tool chạy dưới quyền) trong `.env`, rồi khai báo trong client MCP với URL `http://<máy>:3000/api/v1/mcp/` và header `Authorization: Bearer <MCP_TOKEN>`. Chạy cục bộ qua stdio: `python -m backend.app.mcpserver`.

**Nguồn sách (link mềm):** `GET /api/v1/sources/open?book=<mã>&page=<trang>&q=<câu neo>` mở đúng trang trong thư viện của máy đang chạy, tô sáng câu neo; `/sources/resolve` trả JSON. Danh bạ sách: [books.json](backend/app/knowledge/data/books.json).

**Chạy dưới đường dẫn con.** Ví dụ Tailscale Funnel `--set-path=/bazi`:
- Đặt `PUBLIC_BASE_PATH=/bazi` trong `.env`.
- Thêm origin `https://<máy>.<tailnet>.ts.net` vào `ALLOWED_ORIGINS`.
- Build lại `frontend` và `api`, rồi chạy `up -d frontend api gateway`.
- Gateway nhận cả đường dẫn có lẫn không có `/bazi`, vì Funnel cắt tiền tố trước khi chuyển tiếp. Ở máy local, địa chỉ là `http://127.0.0.1:3000/bazi`.

Người chấm mở `http://127.0.0.1:3000/judge`, nhập mật khẩu chấm và tên. Mỗi câu hỏi hiện câu trả lời, các đoạn sách đưa cho mô hình, và các đoạn truy xuất kèm điểm dense, sparse, trộn và rerank. Phiếu chấm gồm thang 1–5 và nhãn cho từng đoạn. Kết quả tải về dạng CSV. Đoạn được đánh dấu "có quy tắc" vào hàng duyệt của chuyên gia (Tri thức → Luận điểm).

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

Upload cần một pipeline profile (parser/OCR + embedding đã provision); tạo bằng CLI, nên
chạy trong image worker để phiên bản LibreOffice ghi đúng:

```powershell
uv run --locked python -m backend.app.cli pipeline-profile --name "Sách in" --embedding-profile <id> --ocr-languages vie+eng
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

Runbook triển khai (T054). Mọi lệnh chạy ở thư mục repo trên filesystem Linux; Python hệ
thống chỉ dùng cho `scripts/dev`, ứng dụng chạy trong image Python 3.12. Không chép `.venv`,
`.env`, DB hay model qua Git.

### 1. Cài lần đầu

```bash
# Docker Engine + Compose plugin: https://docs.docker.com/engine/install/ubuntu/
git clone https://github.com/nguyentiendat-fenrir/bazi_ai.git && cd bazi_ai
cp .env.example .env && chmod 600 .env
# Điền: POSTGRES_PASSWORD, POSTGRES_APP_PASSWORD, SESSION_SIGNING_KEY, FIELD_ENCRYPTION_KEY,
# BACKUP_ENCRYPTION_KEY (mỗi khóa ≥ 32 ký tự ngẫu nhiên: openssl rand -base64 48),
# APP_ENV=production, BOOKS_DIR (đường dẫn tuyệt đối tới sách). Chép FIELD_ENCRYPTION_KEY và
# BACKUP_ENCRYPTION_KEY ra nơi ngoại tuyến: mất chúng thì lá số và backup không giải mã được.
python3 scripts/dev doctor --target deploy          # phải READY
docker compose --env-file .env -f infra/compose.yaml config --quiet
docker compose --env-file .env -f infra/compose.yaml build
docker compose --env-file .env -f infra/compose.yaml up -d --wait postgres redis
python3 scripts/dev migrate --without-backup         # DB trống, chưa có gì để backup
read -s BAZI_BOOTSTRAP_PASSWORD && export BAZI_BOOTSTRAP_PASSWORD   # không ghi vào history
python3 scripts/dev bootstrap --email admin@example.com
unset BAZI_BOOTSTRAP_PASSWORD
docker compose --env-file .env -f infra/compose.yaml --profile app up -d
```

UI qua gateway `http://127.0.0.1:${GATEWAY_PORT:-3000}` (chỉ loopback; mở ra mạng qua reverse
proxy có TLS). Đăng nhập admin, vào Cài đặt → Hệ thống & ngân sách xem "Vận hành": không có
cảnh báo nào ngoài `BACKUP_MISSING` cho tới backup đầu tiên. Sách: Thư viện → Tải sách lên.

LLM là container `qwen3-8b` (vLLM) có sẵn trên máy, ngoài Compose: `LLM_PROVIDER=openai_compatible`,
`LLM_BASE_URL=http://host.docker.internal:8000/v1`, `LLM_MODEL=qwen3-8b`. Lệnh chạy, VRAM và lý do
các tham số ở [infra/qwen.md](infra/qwen.md). Embedding/reranker Jina chạy CPU, model riêng.

### 2. Backup hằng ngày

```bash
sudo install -d -m 700 -o 10001 -g 10001 /srv/bazi-backups   # ổ khác ổ chạy DB nếu có
python3 scripts/dev backup --dest /srv/bazi-backups --prune   # mã hóa nếu có BACKUP_ENCRYPTION_KEY
```

Lịch (crontab của user chạy Docker): `30 2 * * * cd /srv/bazi_ai && python3 scripts/dev backup
--dest /srv/bazi-backups --prune >> /var/log/bazi-backup.log 2>&1`. `--prune` giữ 7 ngày + 4
tuần. Chép thêm một bản ra máy/ổ khác (rsync thư mục đã mã hóa). Cảnh báo `BACKUP_OVERDUE`
hiện khi bản gần nhất quá 26 giờ.

### 3. Cập nhật phiên bản

Trên Windows: chạy đủ test, commit, `git push origin main`. Trên Ubuntu:

```bash
mkdir -p .cache && git rev-parse HEAD > .cache/previous-commit       # để quay lại
docker image tag bazi-ai-app:local bazi-ai-app:previous             # image đang chạy
python3 scripts/dev backup --dest /srv/bazi-backups                 # bắt buộc trước migrate
git pull --ff-only
python3 scripts/dev doctor --target deploy
docker compose --env-file .env -f infra/compose.yaml build
python3 scripts/dev migrate --status                                # current vs head
python3 scripts/dev migrate --backup-dest /srv/bazi-backups         # từ chối nếu backup > 24 h
docker compose --env-file .env -f infra/compose.yaml --profile app up -d
```

Kiểm sau cập nhật: `/api/v1/health/ready` = ok (admin), trang Vận hành không có cảnh báo mới,
mở một sách và một lá số cũ. Không `reset --hard`, không `compose down -v`; giữ volume
`bazi-ai_*`.

Quay lại khi lỗi: nếu chưa migrate, `git checkout $(cat .cache/previous-commit)`, tag lại
`bazi-ai-app:previous` thành `:local` và `up -d`. Nếu đã migrate, migration mới có thể
`downgrade` (mỗi migration ghi bước rollback trong docs/15), nhưng an toàn nhất là restore
backup vừa tạo vào project mới (mục 4), kiểm, rồi chuyển.

### 4. Restore và diễn tập

```bash
python3 scripts/dev restore-preflight --manifest /srv/bazi-backups/<tên>/manifest.json
python3 scripts/dev deletion-ledger --dest /srv/bazi-backups        # người đã bị xóa từ đó
python3 scripts/dev restore --manifest /srv/bazi-backups/<tên>/manifest.json --confirm <tên> \
    --deletion-ledger /srv/bazi-backups/deletion-ledger.json
python3 scripts/dev drill --manifest /srv/bazi-backups/<tên>/manifest.json --confirm <tên>
```

Restore luôn vào project `bazi-restore` với volume mới, không ghi đè hệ thống đang chạy;
chạy thử ở cổng khác (`GATEWAY_PORT=3001 … -p bazi-restore --profile app up -d`), chuyển khi
kiểm xong, giữ volume cũ một thời gian. `drill` làm cùng việc vào `bazi-drill` rồi gỡ project
đó; nên chạy hằng tháng và ghi thời gian (RTO) báo ra. Chi tiết: [docs/12](docs/12_SECURITY_OPERATIONS.md#restore-runbook-bắt-buộc-kiểm-thử).

### 5. Theo dõi

Trang Cài đặt → Hệ thống & ngân sách (admin): cảnh báo ổ đĩa, backup, job lỗi lặp, hàng đợi
kẹt, ngân sách, embedding; số liệu hàng đợi/lỗi/độ trễ tra cứu. `GET /api/v1/operations/metrics`
cho công cụ ngoài. Log là JSON trên stdout của từng container (`docker compose logs api`).
