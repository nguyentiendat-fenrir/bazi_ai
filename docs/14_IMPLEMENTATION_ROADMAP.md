# 14 · Lộ trình từ repository đặc tả tới sản phẩm đầy đủ

## Lộ trình hiện hành — ADR-21, 17/10/2026

Thay thứ tự tuần tự mặc định; giữ yêu cầu release đầy đủ và dependencies task cha.
T057 chỉ cấu trúc/preflight/roadmap, không làm UI ngay theo xác nhận chủ dự án.

| Mốc | Tasks | Kết quả/gate |
|---|---|---|
| K0 Cấu trúc + corpus | T057; T001 đã pass | Windows dev, inspector Linux, 7 file/815 trang, bảo toàn nguồn |
| K1 Foundation Ubuntu | T002 → T003–T008 | Runtime/migrations/auth/storage/API thật; không gate WSL máy dev |
| K2 Kho tài liệu | T009–T019 | Native/OCR, DOCX, review, chunk/embed/publish; pilot rồi mở rộng |
| K3 Tri thức | T020–T025 | Author/school layers, review, ontology/cases/gold; không autoapprove |
| K4 RAG | T035–T038 | Hybrid/rerank/citations, Gemma llama.cpp adapter; measured evaluation |
| K5 UI kho/vận hành | Subtasks dưới; T047/T048 theo deps gốc | Library/jobs/review; backup/restore và security trước sử dụng lâu dài |
| K6 Lá số/luận giải | T026–T034, T039–T045 và UI còn lại | Oracle/calendar/DSL/chat; không bỏ phạm vi gốc |
| K7 Release đầy đủ | T049–T056 | Security/recovery/scale và tám kịch bản cuối |

Subtasks tách để không phải chờ full chart/chat (task cha chỉ done khi đủ nghiệm
thu gốc):

- T043.1 shell/auth/library navigation: sau T006 + T008; T043.2 tích hợp đầy đủ
  vẫn sau T042.
- T046.1 library/upload/jobs/OCR review: sau T043.1 + T019, endpoints thật, test
  upload→review→publish, 412/forbidden; T046.2 full UI vẫn sau T045.
- T038.1 llama.cpp/config/timeout/model ID: sau T008; T038 đầy đủ giữ T008 + T024
  cùng budgets/mocks/usage và no-provider gates.
- T025.1 soạn ≥70 câu/relevant spans: sau T014; T025 đầy đủ sau T024 và duyệt gold.
- T052.1 backup DB/objects/checksums: sau T019; T053.1 restore kho trên volumes mới:
  sau T052.1. Làm trước dùng kho thật lâu dài; T052/T053 đầy đủ vẫn giữ deps/gates.

Security test theo module bắt buộc ngay, không chờ T049. `evidence/task_graph.json`
là graph bàn giao lịch sử, không scheduler hiện hành. Phần dưới giữ để truy vết
phạm vi full release, không còn là thứ tự chạy mặc định.

## Thứ tự mặc định

Chạy T001→T056. TASKS.md là nguồn phụ thuộc chính; các mốc dưới đây nhóm công việc, không thay dependency graph. Chưa ước tính số ngày chính xác khi chưa biết tốc độ Codex, môi trường và chuyên gia thẩm định. Chốt thời gian sau milestone hạ tầng đầu và benchmark.

| Milestone | Tasks | Sản phẩm kiểm tra được | Gate chuyển mốc |
|---|---|---|---|
| M0 Bảo toàn/khởi tạo | T001–T003 | legacy immutable, lock/Compose, FastAPI skeleton | Source checksums + doctor + core logs/errors |
| M1 Data/API foundation | T004–T008 | schema, auth/RLS, storage adapters, typed contracts | Empty DB migrations + owner/privacy + object roundtrip |
| M2 Document processing | T009–T019 | batch upload→native/OCR/DOCX→index→publish; retry/correction/reprocess | 613 mẫu + scan/mixed fixtures, kill/retry, atomic release |
| M3 Structured knowledge | T020–T025 | scoped terms/assertions/rules/cases, review, dependency graph, gold draft→verified | Không autoapprove, cases provenance, expert gold |
| M4 Calculation | T026–T030 | reusable verified chart engine, time policies, profiles/charts API | Oracle boundary tests và sửa lỗi A01/A02/A04/A05 |
| M5 Rule Engine | T031–T034 | DSL, tri-valued, DAG, conflict trace, approved ruleset/re-evaluate | No arbitrary execution, exact trace fixtures |
| M6 Retrieval | T035–T037 | hybrid scope/filter/expansion/fusion/rerank/citations | Held-out retrieval+source page gates |
| M7 AI/chat backend | T038–T042 | providers/budget, 3 modes, memory/history/SSE/client contracts | Empty/no-model + supported claims + replay tests |
| M8 Frontend đầy đủ | T043–T048 | chart/chat/library/admin/cases/evaluation/settings flows | Playwright real backend, no demo-only behavior |
| M9 Quality/operations | T049–T055 | security/deletion, harness, benchmark, backup/restore, WSL guide | Security gates + restore drill + Windows execution |
| M10 Bàn giao | T056 | Release manifest/code/docs/test evidence | E2E01–08 và chuyên gia thẩm định pass |

## Đường phụ thuộc cần chú ý

Calculation T026 phụ thuộc T008, không cần sách đã nhập; T029 oracle có thể thu thập trong khi các task không liên quan hoàn thiện nhưng không đánh dấu done giả. Rules T031 cần ontology T024 và facts T030; reasoning T039 cần rule impacts T034, citations T037 và adapters T038. Frontend chức năng cần full contract T042; có thể dựng static shell sớm nội bộ nhưng không ghi UI task done trước backend. Backup không là hạng mục “sau này”, nằm trước release.

## Quy tắc checkpoint và tiếp tục

Sau mỗi task: tests+report+git commit, ghi next task ready; không tự sửa checklist lịch sử nếu không đọc evidence. Phiên Codex sau đọc AGENTS/TASKS/git diff/reports trước khi tiếp tục. Nhiệm vụ bị chặn ghi issue ID và blocker thực tế, chọn task ready khác nếu không phá topological dependencies. Không bỏ core requirement chỉ để giữ tất cả checkbox xanh.

Ba PDF là dữ liệu kiểm thử, không phải prerequisites của repository foundation/chart/DSL unit tests. Khi chưa có sách, fixtures synthetic chứa metadata `synthetic_test`; không xuất hiện như tri thức đã duyệt. File RAR là prerequisite tái sử dụng engine; nếu thiếu trên máy Codex, chỉ chặn T001 phần source và T026–T030, làm tiếp setup độc lập có ghi rõ.

## Các quyết định cần người có chuyên môn tham gia

T025 duyệt gold query/span và speaker; T029 duyệt lịch/policy/auxiliary; T033 duyệt rules từ sách và exceptions; T050 kiểm semantic support mẫu. Đây là kiểm chứng nghiệp vụ có deliverable cụ thể, không là yêu cầu hỏi lại những gì đã có trong prompt. Codex chuẩn bị fixtures/report/diff đầy đủ trước khi trình duyệt; không bắt người dùng tự thiết kế lại.

## Không nằm trong release

Native mobile, thanh toán, public deployment, multi-tenant thương mại, avatar và cluster phân tán. S3 adapter, OCR scan, rule approval, case library, evaluation, backup và privacy đều **nằm trong** release này. Hỗ trợ thêm calendar ngoài capability đã kiểm chứng đi qua adapter+oracle, không được silently substitute.
