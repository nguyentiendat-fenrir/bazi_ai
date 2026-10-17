# 01 · Master specification

## Sản phẩm và phạm vi bàn giao

BAZI AI là chatbot nghiên cứu và diễn giải Bát Tự gồm ba khối tách biệt:

1. **Kho tri thức từ sách** — nhập PDF/DOCX, giữ nguồn bất biến, tách trường phái và
   lớp tác giả/bình chú, tra cứu hybrid có dẫn nguồn ([05](05_DOCUMENT_PIPELINE.md),
   [06](06_KNOWLEDGE_MODEL.md), [07](07_RAG_ENGINE.md)).
2. **Engine tính lá số** — deterministic, không gọi LLM, kèm Rule Engine độc lập
   ([08](08_BAZI_ENGINE.md)).
3. **LLM suy luận** — trả lời câu hỏi người dùng chỉ trên facts, rules và evidence
   đã kiểm, citation do backend xác thực ([09](09_AI_REASONING.md)).

Diễn giải mệnh lý là tri thức truyền thống có trường phái, không tuyên bố là dự
báo khoa học. Máy dev là Windows; runtime là Ubuntu 22.04 với Docker Compose, cùng
host với Gemma llama.cpp ([12](12_SECURITY_OPERATIONS.md)). Không có public
hosting, mobile native, thanh toán hay multi-tenant trong release này.

Thứ tự thực hiện: **kho tri thức trước**, rồi lá số và chat
([14](14_ROADMAP.md), ADR-21). R01–R11 dưới đây là mục tiêu release đầy đủ, chưa
phải chức năng đã triển khai; trạng thái từng task ở 14.

Một admin có thể tạo thêm tài khoản reader/reviewer. Tất cả module dưới đây bắt buộc nằm trong release: calculation, profiles/charts, PDF/DOCX batch intake, OCR/layout/corrections, document store, terminology/schools/rules/cases, Hybrid RAG/reranker/citations, independent Rule Engine, ba chế độ chatbot, dashboard quản trị, evaluation, security, backup/restore và observability.

## Yêu cầu chuẩn

| ID | Yêu cầu bắt buộc | Tài liệu | Task ([14](14_ROADMAP.md#danh-sách-task)) |
|---|---|---|---|
| R01 | Cài local với kho trống, seed chỉ ontology và settings; không seed bằng chứng giả | 03,12 | T001–T008,T048 |
| R02 | Tái dùng mã lập lá số; policy lịch tường minh; oracle và regression | 02,08 | T026–T030 |
| R03 | Nhập PDF/DOCX nhiều tệp; checksum, quarantine, batch, resume | 05 | T009–T019 |
| R04 | Immutable source revisions; page/block/table/case provenance | 04,05,06 | T011–T017,T023 |
| R05 | Thẩm định rules và tách trường phái/tác giả/bình chú | 06,08 | T020–T024,T031–T034 |
| R06 | Hybrid lexical/vector, expansion, filters, fusion, reranker | 07 | T025,T035–T037 |
| R07 | Research/Chart/Comparison, multi-turn, tools, streaming | 09 | T038–T042 |
| R08 | 13 khu vực UI dùng API thực; rỗng/loading/error đầy đủ | 11 | T043–T048 |
| R09 | Theo dõi impact, revoke, sửa OCR incremental không ngắt chat | 05,06 | T017,T019,T024,T034 |
| R10 | Test bảo mật, giới hạn tài nguyên và chi phí; backup/restore | 12,13 | T049–T055 |
| R11 | Tám kịch bản cuối pass có bằng chứng | 13 | T056 |

## Bất biến không được phá vỡ

1. Chart facts chỉ từ Calculation Engine. Cùng input chuẩn hóa, policy và engine version phải có cùng content hash; không phụ thuộc timezone của container.
2. Dẫn nguồn gồm source version + immutable page revision + offset/block/bbox, không chỉ tên sách và số trang gõ tay. Nguồn phải có quyền truy cập và đã publish tại thời điểm retrieval.
3. Rule draft/candidate/revoked không thực thi. Rule set là snapshot immutable; cập nhật tạo bản mới. Hai school chạy hai trace riêng.
4. Không có sách: retrieval trả `empty_corpus`; chat vẫn lưu hội thoại và giải thích giới hạn; chart vẫn tính được; admin vẫn upload được. Không có model: `provider_not_configured`, không spinner vô hạn.
5. Publish dataset mới atomic. Chat đang chạy ghim snapshot cũ, job lỗi không xóa tập đang dùng. Security withdrawal có hiệu lực ngay cả với snapshot đang chạy.
6. Job có thể giao nhiều lần; mỗi stage/page chỉ có một kết quả hợp lệ cho một input hash và pipeline version. Celery là tín hiệu thực thi, PostgreSQL là nguồn trạng thái thật.
7. Thêm sách/cập nhật cấu hình không cần sửa code. Schema cho tối thiểu 1.000 đầu sách, 100.000–500.000 trang benchmark; không cam kết thời gian xử lý khi chưa đo.
8. Không trộn “dụng” Manh Phái với “dụng thần” ở các lớp Tử Bình. Alias chỉ mở rộng trong concept scope đã duyệt.

## Quyền và dữ liệu

Reader xem kho đã xuất bản và hồ sơ/hội thoại của chính mình. Reviewer thêm quyền xử lý OCR, metadata và đề xuất/duyệt tri thức; admin thêm quyền user/settings/operations. Một người local có thể vừa tác giả vừa duyệt nhưng phải thao tác duyệt tường minh và ghi log; không yêu cầu người thứ hai để sử dụng cá nhân. Dữ liệu sinh không tự đưa vào kho sách hoặc case công khai.

## Giả định thiết kế

Giới hạn ngày sản phẩm đầu: 1900-01-01 đến 2100-12-31 theo Gregorian; ngày ngoài khoảng trả lỗi rõ. Dữ liệu lịch âm nhập có cờ tháng nhuận và calendar_system bắt buộc. Hỗ trợ `chinese_lunisolar` qua adapter đã kiểm chứng; `vietnamese_lunisolar` chỉ nhận khi implementation có oracle đạt gate, nếu chưa thì 422 UNSUPPORTED_CALENDAR, tuyệt đối không đổi nhãn lịch Trung Quốc thành lịch Việt. Tất cả đường nhập Gregorian vẫn hoạt động đầy đủ.

Policy mặc định sau khi đạt kiểm thử: năm tại Lập Xuân, tháng tại 12 tiết mở tháng; ngày đổi 00:00; giờ dân sự, không tự hiệu chỉnh kinh độ. Có lựa chọn 23:00/giờ Mặt Trời trong cùng release. Chuẩn hóa các lựa chọn thành versioned policy, UI luôn hiện policy. Dữ liệu chỉ biết khoảng giờ tạo tập biến thể, không chọn đại một giờ.

## Nghiệm thu sản phẩm

T056 phải chứng minh tám kịch bản trong [13](13_TEST_PLAN.md#tám-kịch-bản-nghiệm-thu-cuối), kể cả thêm 100 tài liệu không sửa code, job lỗi không ảnh hưởng sách khác, thay rule xác định được analysis bị stale, restore trên volumes sạch. Vận hành local không đồng nghĩa offline tuyệt đối: LLM API cần Internet, tải model lần đầu cần Internet; engine và kho sách vẫn hoạt động khi mất mạng.
