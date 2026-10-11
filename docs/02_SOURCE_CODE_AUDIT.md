# 02 · Audit mã nguồn và ba PDF

**Audit thực hiện 10–11/10/2026.** Phân biệt: VERIFIED_STATIC (đọc code/bytes), REPRODUCED (chạy probe), SAME_LIBRARY_COMPARISON (không độc lập), NEEDS_ORACLE (chưa xác minh nghiệp vụ). File này đáp ứng yêu cầu SOURCE_CODE_AUDIT.md trong cấu trúc đánh số đã chọn.

## 1. Phạm vi tìm và đầu vào thực đọc

Đã tìm trong Library và truy xuất ngữ cảnh hội thoại dự án AI Bát Tự qua công cụ Personal Context. Không có API chứng nhận đã duyệt tuần tự mọi message trong project; vì vậy không tuyên bố đã đọc toàn bộ lịch sử từng dòng. Bốn tệp yêu cầu đã tìm thấy, tải được bytes và kiểm tra trực tiếp. Có thêm bản tên cao cấp `(1)` cùng kích thước trong kết quả tìm; audit chọn bản **không `(1)` đúng tên yêu cầu**, không giả hai file cùng hash khi chưa so bytes.

| Tệp | Bytes | SHA256 |
|---|---:|---|
| bazi.rar | 35.305.832 | `9409da54f27b9eb11ee38ff7ebb09903d99c7d835a2bef8eff0d99d6c3cdd9c3` |
| Manh phái sơ cấp lý pháp Facebook ánh dương .pdf | 1.667.843 | `3735ab14d8e6d51effa33efce6e428b2bd93fc2fe997e6dd5ba4f0b508e468ad` |
| Manh phái cao cấp - Đoàn kiến Nghiệp - tài liệu giảng dạy facebook sách ánh dương .pdf | 1.412.304 | `41dcafa5ce08d5dd0e0b1d480864cf0c853756ded9b6712f829baf10d53ff321` |
| Tử Bình Chân Thuyên bình chú.pdf | 2.822.271 | `4466e2a80c858fe373584b50dc2e753e89f61c815925d75a0f2a0bf6bd4d255e` |

## 2. Archive inventory và dependencies

RAR có 1.444 entries gồm thư mục, 43.471.231 bytes tổng uncompressed. Đã kiểm kê toàn archive, giải nén phần source nghiệp vụ (10 tệp gồm .gitignore) và chỉ trích xuất source `.py` của lunar_python để chạy; không chạy Windows `.venv`, install script hoặc binary trong archive.

| Module/file | Quy mô / vai trò | Phân loại tái sử dụng |
|---|---|---|
| backend/bazi.py | 680 dòng, 32.802 bytes; tables + functions + CLI | Tái sử dụng nhưng tách module, sửa timezone/EOT/Lưu Niên, bổ sung oracle |
| backend/main.py | 50 dòng; FastAPI health và POST /api/bazi | Tái dùng ý tưởng wrapper, refactor route/validation/errors/auth/CORS |
| backend/schemas.py | 16 dòng; BaziRequest/BaziResponse | Thay schema public bằng typed contract v1; adapter giữ legacy payload |
| backend/requirments.txt | 4 dependencies, tên thiếu chữ e | Thay bằng pyproject+lock; không dùng unpinned lunar-python |
| backend/uvicorn_run.sh | 3 dòng; bind 0.0.0.0, 2 workers | Thay bằng Compose startup local và gateway loopback |
| frontend/index.html | 171 dòng; form/bảng lá số | Tái sử dụng bố cục thông tin; migrate Next.js, không copy UI như sản phẩm đủ |
| frontend/app.js | 358 dòng; render, hardcoded API localhost | Refactor React+typed client; timezone input là trọng điểm |
| frontend/style.css | 215 dòng | Có thể tái sử dụng quy ước màu/ngũ hành sau UX review |
| README.md | Một dòng “# bazi” | Viết lại hướng dẫn triển khai |

Dependencies khai báo: fastapi==0.115.0, uvicorn[standard]==0.30.6, pydantic==2.9.0, lunar-python không pin. Inventory `.venv` có lunar_python-1.4.4.dist-info; bản source đó được dùng trong probe. Không có project test suite/migrations/Docker/DB/auth/RAG trong source nghiệp vụ kiểm kê. Không lấy môi trường `.venv` là dependency lock có thể tái lập.

## 3. Luồng tính toán hiện tại

InputArgs gồm dt datetime, tz string, gender, method standard/true_solar_time, lon optional. API nhận dt string bằng datetime.fromisoformat. Frontend ghép datetime **không offset**, gửi timezone riêng, luôn `method:"standard"` nên chưa có true-solar UI. Backend gọi args.dt.astimezone(tzinfo), tùy chọn cộng correction, rồi Solar.fromYmdHms(...).getLunar().getEightChar().

Year/month/day/time từ lunar_python → map chữ Hán sang Việt. Tàng Can từ AN_TANG; Thập Thần từ quan hệ sinh/khắc/âm-dương; Nạp Âm bảng 60; Trường Sinh theo điểm đầu và chiều can âm/dương; Không Vong dùng tuần ngày. Quan hệ chi duyệt các cặp và set tam hợp. Điểm ngũ hành cộng can 1.0 và tàng can [1.0,0.5,0.3], chưa có nguồn kiểm chứng cho dùng để kết luận vượng nhược.

Đại Vận gọi getYun(sex), mặc định sect 1 của thư viện, lấy các vận bỏ index 0 rồi tự bù đến 10. Lưu Niên tự tiến can/chi từ trụ năm sinh và gắn năm_dương=birth_year+k. Cung Mệnh dùng bảng can năm và công thức chi 26-(tháng+giờ). Thai Nguyên dùng -9 cho vòng can/chi.

Output legacy gồm đầu_vào, trụ, điểm_ngũ_hành, quan_hệ_chi, đại_vận, lưu_niên, cung_menh, thai_nguyen. Không có schema version/engine manifest, không lưu rule provenance. Không có nhập lịch âm explicit ở API; việc thư viện có Lunar không có nghĩa sản phẩm đã hỗ trợ lịch Việt/tháng nhuận đúng.

## 4. Findings có bằng chứng

| ID / mức | Vị trí và kiểm tra | Kết quả / xử lý |
|---|---|---|
| A01 critical, REPRODUCED | bazi.py 396–398; frontend 309–318; naive datetime | Input tổng hợp 2000-06-15 05:30 Asia/Ho_Chi_Minh: host UTC thành 12:30, trụ giờ Canh Ngọ; host Việt vẫn 05:30, Đinh Mão. Aware +07:00 giữ 05:30. Phải localize tường minh |
| A02 high, REPRODUCED | equation_of_time_minutes 287–291 | Dùng góc 2π(N−81)/364 với hệ số của công thức fractional-year khác. 2024-02-11 ra +13,317 phút, NOAA reference tính −14,195; 2024-11-03 ra −4,553 so reference +16,362. Sửa/đối chiếu EOT và không double-correct |
| A03 high, VERIFIED_STATIC + probe | solar local fields 410; lunar lib ShouXingUtil ONE_THIRD | Thư viện có bù 1/3 ngày (8h) cho mốc thiên văn, adapter không đổi chuẩn tiết khí. Lib cho Lập Xuân 2024 16:26:53; backend UTC+7 15:30 còn Quý Mão/Ất Sửu và 16:30 đổi Giáp Thìn/Bính Dần. Cần chuyển instant UTC+8→UTC; chưa có oracle độc lập đến giây trong phiên |
| A04 high, REPRODUCED | build_luu_nien 375–390, call 559 | Sinh 15/01/2024, danh sách ghi 2024 Quý Mão, 2025 Giáp Thìn. Đây là nhãn năm dương sai ngữ nghĩa chu kỳ năm tiết khí; phải dùng Lập Xuân intervals |
| A05 high, REPRODUCED/static | resolve_timezone 306–327; schemas | Invalid/Zone fallback UTC và chỉ print; gender khác M mặc định female, method lạ mặc định standard, lon chưa range validate. Từ chối lỗi thay vì thay input |
| A06 medium, REPRODUCED | phan_tich_quan_he_chi 264–282 | Có Thân/Tý, thiếu Thìn vẫn vào key tam_hợp; không có completeness. Cần phân partial/full; không kết luận đã hóa. Set iteration cũng gây order không ổn định |
| A07 VERIFY, SAME_LIBRARY_COMPARISON | tinh_thai_nguyen 140–149 | **Không xác nhận lỗi Thai Nguyên**. -9 mod10=+1, -9 mod12=+3; 12 tháng năm 2024 khớp getTaiYuan. Comment “lùi 10 tháng” cần làm rõ, không tự sửa phép tính đúng chỉ vì comment |
| A08 high, NEEDS_ORACLE | getEightChar default sect=2; getYun sect=1 | Chưa expose chính sách 23h/00h, phương pháp khởi vận; chưa kiểm toàn bộ lịch sử timezone, DST, giờ Mặt Trời, sai số tiết khí |
| A09 medium, VERIFIED_STATIC | đại vận 493–557 | Tự bù 10 vận, catch rộng, biến gan_vi/zhi_vi có thể giữ giá trị vòng trước khi exception. Cần fail/unknown typed và interval tests; smoke count=10 không chứng minh khởi vận đúng |
| A10 medium, VERIFIED_STATIC | Cung Mệnh, element scores, growth stages | Có logic và bảng để tái dùng nhưng chưa chuyên gia xác minh mọi trường phái. Không dùng heuristic weights làm fact mệnh lý |
| A11 high, VERIFIED_STATIC | main.py CORS/exception | wildcard credentials, không auth; exception trả ok:false 200 và str(e). Thay error contract, ACL, redaction |
| A12 medium, VERIFIED_STATIC | frontend/backend glue | Hardcoded URL, chưa persist, chưa API versioning; nhiều rendering innerHTML có esc text nhưng không đủ cơ sở gọi là hoàn toàn an toàn. Không báo exploit đã chạy |

## 5. Kiểm thử thực chạy và giới hạn

Python 3.12.14 Linux, source nghiệp vụ không sửa + lunar_python đi kèm 1.4.4. Đã chạy `audit/probe.py` và `audit/test_observations.py`; **9 observation tests pass**. Đây là tests xác nhận hành vi hiện tại, trong đó có test cố ý xác nhận lỗi; không phải 9 tests chứng nhận engine đúng. 12 Thai Nguyên comparisons dùng chính thư viện, không oracle độc lập. Smokes leap day/aware time/10 vận chỉ xác nhận chạy được.

Chưa chạy server HTTP FastAPI, browser UI, Docker, test Windows thật, sxtwl độc lập, HKO exact second đối chiếu, full 60/120 combination tables, mọi Đại Vận/Cung Mệnh. Truy cập trang HKO 2024 cụ thể không thành công qua công cụ; không bịa bảng đã tải. T026–T030 tiếp tục kiểm này; bug A01/A02/A04/A05 có gate chặn release.

## 6. PDF audit

Quét text/metadata trên **tất cả 613 trang** bằng PyMuPDF; đọc nội dung chọn lọc theo cấu trúc/thuật ngữ, render và xem 9 trang đại diện. Không tuyên bố đã thẩm định học thuật từng câu toàn bộ 613 trang, không đo OCR accuracy khi chưa có gold transcription.

| Mẫu | Trang | Ký tự text strip tổng | Nhận xét |
|---|---:|---:|---|
| Manh sơ cấp | 292 | 286.241 | Text native; không embedded raster theo get_images; các bảng căn dòng vẫn cần layout parsing |
| Manh cao cấp | 181 | 198.338 | Text native; trang 5 gần trống (<100 chars), ảnh ở trang 30 |
| Tử Bình | 140 | 451.278 | Text native dày; ảnh ở trang 77; nhiều bảng và lớp chú giải/màu chữ |

Cả ba không có PDF bookmark TOC theo get_toc, nhưng có mục lục in trong text. Số trang đầu text khớp physical index trên 613/613 trang theo heuristic, visual samples cũng khớp. Không hardcode `printed=physical` cho sách tương lai; lưu cả hai, trạng thái verified theo từng trang được kiểm. Phát hiện ảnh không đồng nghĩa PDF scan; “không ảnh embedded” không loại trừ vector hình/sơ đồ.

Sơ cấp: mục lục trang 1–3; chương 1 tại 13, Khách–Chủ 16–18, Thể–Dụng 18–20, Tố Công 26–27, kiến thức bổ sung chương 3 tại 118. Nội dung dùng định nghĩa, điều kiện và mệnh lệ; nhiều đoạn tiếp từ trang trước. Trang 19 nêu rõ dụng trong Manh Phái khác dụng thần của truyền thống — thiết kế cần concept scopes.

Cao cấp: mục lục 2–4; chương Ứng Kỳ từ 6, Tượng Pháp từ 19; trang 7 có hàng Tứ Trụ và Đại Vận, trang 10 mệnh lệ với số tuổi vận. Trang 30 có thiên văn đồ/12 địa chi; giữ ảnh gốc, OCR vùng hình không thay toàn trang native. Quy tắc ứng kỳ trang 6–7 cần nguyên cục+đại vận+lưu niên, không chuyển thành if một chữ thì sự kiện chắc chắn.

Tử Bình: đầu sách nêu tác giả Thẩm Hiếu Chiêm, Từ Nhạc Ngô bình chú; chương 1 ở 5, chương 8 Luận Dụng Thần tại 26. Có Nguyên văn/Nguyên chú, Từ chú và Lâm chú ở mẫu trang 28. Native text extraction làm mất màu, có thể trộn tầng phát ngôn; layout/font metadata và text markers phải cùng được dùng. Trang 26–30 có bảng 4 trụ và phương pháp luận, khác scope với Thể–Dụng Manh Phái. Không cho một nhãn “Tử Bình” xóa khác biệt nguyên tác/bình chú.

## 7. Quyết định rút ra từ audit

Ưu tiên sửa/tách engine thay vì viết lại. Dùng parser adapter/page blocks/source map thay vì dump text→vector. Native extraction là đường đầu cho ba mẫu; OCR route vẫn bắt buộc thử bằng synthetic scanned/mixed fixtures để hệ thống không phụ thuộc ba sách. Seed câu hỏi gold trỏ trang thật, nhưng câu trả lời/điều kiện phải được chuyên gia duyệt. Số “829 đoạn” trong hội thoại trước không được tái tạo ở phiên này, không dùng làm chỉ tiêu chunking hay tuyên bố index đã sẵn sàng.

## 8. Tái lập bằng chứng trong gói

`evidence/source_manifest.json` ghi hash source nghiệp vụ và source lunar_python đã dùng; `legacy_probe_results.json` và `legacy_observation_tests.txt` là output lần chạy thực. `pdf_metrics.json` chứa thống kê từng trang, không chứa toàn văn sách. Các script chỉ dành cho audit, không phải application tests đã sửa lỗi.

Sau T001, đặt lunar_python đúng bản 1.4.4 đã đối chiếu vào audit/vendor (hoặc cài dependency đúng bản trong audit venv); xác minh hash manifest. Chạy trong WSL/Linux vì kiểm host TZ dùng time.tzset:

```bash
BAZI_AUDIT_BACKEND=legacy/bazi/backend BAZI_AUDIT_VENDOR=audit/vendor python evidence/test_legacy_observations.py
BAZI_AUDIT_BACKEND=legacy/bazi/backend BAZI_AUDIT_VENDOR=audit/vendor python evidence/reproduce_probe.py
```

Nếu code đã sửa, các observation tests cố ý kiểm bug sẽ không còn pass; giữ legacy để tái hiện, viết regression tests mới trong backend để đòi hành vi đúng. Không sửa code hiện tại cho quay lại bug để các observation tests pass.
