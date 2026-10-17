# Tài liệu BAZI AI

Chatbot Bát Tự gồm ba khối: **kho tri thức từ sách**, **engine tính lá số** và
**LLM suy luận**. Hiện tập trung xây kho tri thức trước; xem [14](14_ROADMAP.md).

## Đọc theo thứ tự

| Bước | Tài liệu | Dùng khi |
|---|---|---|
| 1 | [01 · Master spec](01_MASTER_SPEC.md) | Phạm vi sản phẩm, yêu cầu R01–R11, bất biến |
| 2 | [14 · Lộ trình và task](14_ROADMAP.md) | Việc đang làm, thứ tự, trạng thái từng `T0xx` |
| 3 | [03 · Kiến trúc](03_ARCHITECTURE.md) | Hiện trạng vs đích, module contracts, transaction/event |
| 4 | [15 · ADR](15_ARCHITECTURE_DECISIONS.md) | Quyết định đã chốt/đang thử nghiệm, decision log |

## Theo khối chức năng

| Khối | Tài liệu |
|---|---|
| Kho tri thức | [05 · Pipeline tài liệu](05_DOCUMENT_PIPELINE.md) (corpus hiện tại, stages, OCR, locator) · [06 · Tri thức có cấu trúc](06_KNOWLEDGE_MODEL.md) · [07 · Hybrid RAG](07_RAG_ENGINE.md) |
| Engine lá số | [08 · Calculation và Rule Engine](08_BAZI_ENGINE.md) · [02 · Audit mã nguồn cũ và PDF](02_SOURCE_CODE_AUDIT.md) |
| LLM và chat | [09 · AI Reasoning](09_AI_REASONING.md) |
| Hợp đồng dữ liệu | [04 · PostgreSQL schema](04_DATABASE_SCHEMA.md) · [10 · REST/SSE API](10_API_SPEC.md) |
| Giao diện | [11 · Frontend UX](11_FRONTEND_UX.md) |
| Vận hành và chất lượng | [12 · Bảo mật, triển khai, backup](12_SECURITY_OPERATIONS.md) · [13 · Test plan và release gates](13_TEST_PLAN.md) |

## Quy ước

- 04 và 10 là hợp đồng: đổi schema/API cần ADR trong 15 và cập nhật cả hai.
- Số liệu "đã đo" luôn ghi ngày và công cụ; ngưỡng chưa benchmark ghi rõ là mục tiêu.
- Trạng thái task chỉ cập nhật ở 14; tài liệu khác chỉ tham chiếu mã task.
- Quyết định kỹ thuật mới (phiên bản, model, tham số đã đo) ghi vào decision log của 15.
