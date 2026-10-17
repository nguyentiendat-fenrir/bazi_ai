# 01 · Master specification

## Điều chỉnh triển khai — 17/10/2026, ADR-21

Ưu tiên kho tri thức/RAG; dev Windows native, runtime OCR Ubuntu 22.04 cùng host
với Gemma llama.cpp. Yêu cầu WSL2 máy dev và thứ tự tuần tự cũ được thay bằng
TASKS/docs/14. R01–R11 vẫn là mục tiêu release đầy đủ; T057 không phải bàn giao
ứng dụng. Không thay schema/API/facts engine.

## Sản phẩm và phạm vi bàn giao

BAZI AI là nền tảng nghiên cứu và diễn giải Bát Tự chạy local Windows qua WSL2/Docker, chuyển được lên Linux bằng cùng containers. Tính toán lịch là deterministic; diễn giải mệnh lý là tri thức truyền thống có trường phái, không tuyên bố là dự báo khoa học. Không có public hosting, mobile native, thanh toán hay multi-tenant trong release này.

Một admin có thể tạo thêm tài khoản reader/reviewer. Tất cả module dưới đây bắt buộc nằm trong release: calculation, profiles/charts, PDF/DOCX batch intake, OCR/layout/corrections, document store, terminology/schools/rules/cases, Hybrid RAG/reranker/citations, independent Rule Engine, ba chế độ chatbot, dashboard quản trị, evaluation, security, backup/restore và observability.

## Yêu cầu chuẩn

| ID | Yêu cầu bắt buộc | Chủ sở hữu thiết kế | Task |
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

T056 phải chứng minh tám kịch bản trong 13, kể cả thêm 100 tài liệu không sửa code, job lỗi không ảnh hưởng sách khác, thay rule xác định được analysis bị stale, restore trên volumes sạch. Vận hành local không đồng nghĩa offline tuyệt đối: LLM API cần Internet, tải model lần đầu cần Internet; engine và kho sách vẫn hoạt động khi mất mạng.
