# 06 · Structured BaZi Knowledge

## Hai lớp tri thức

Document Knowledge Store là bản gốc, revisions, chunks, embeddings và locator. Structured KB là khái niệm/quan điểm/rule/case có phiên bản và evidence. Vector gần nhau không chứng minh hai thuật ngữ cùng nghĩa. Structured candidate có thể được tạo tự động nhưng chưa là tri thức được thẩm định.

Ontology seed chỉ chứa mã Can/Chi, taxonomy trường phái, loại thực thể, không chứa diễn giải giả có citation. `school` có `parent_id` và `method` versioned; trường phái sách do admin xác nhận, AI chỉ gợi ý. Một sách chứa nhiều quan điểm được gán ở section/assertion scope, không áp một trường phái cho mọi đoạn.

## Concept, term và assertion

- Concept identity: `(school_id, canonical_key)`; label tiếng Việt, chữ Hán nullable, description revision, aliases có scope/source.
- Term form: NFC exact, folded no-accent search; quan hệ `same_concept`, `translation_variant`, `related`, `contrasts_with`. Chỉ `same_concept/translation_variant` đã duyệt được expansion, theo selected school/method.
- Assertion: một phát biểu có `claim_type`, `school_id`, `method_id`, `speaker_layer`, applicability, exception_text, revision, evidence spans và review state. Phân biệt `source_explicit`, `editor_interpretation`, `ai_inferred`.
- Các lớp phát ngôn: `original_author`, `commentator`, `translator`, `editor`, `unknown`; tên speaker chỉ ghi khi tài liệu xác nhận. Tử Bình có Nguyên văn/Nguyên chú, Từ chú và các chú giải khác: không gán mọi chữ vào Thẩm Hiếu Chiêm.
- Relations giữa assertions: supports, disputes, qualifies, exception_to, derives_from. Quan hệ do AI gợi ý cũng phải review. Chỉ quan hệ đúng revision mới đưa vào run.

## Các ví dụ dựa trên sách đã đọc

| Concept scope đề xuất | Bằng chứng trong mẫu | Cách dùng |
|---|---|---|
| `manh_phai.khach_chu` | Sơ cấp trang PDF 16–18 | Khái niệm có nhiều cấp; không cứng hóa “chủ luôn chỉ là can ngày” |
| `manh_phai.the_dung` | Sơ cấp 18–20, đặc biệt 19 | “Dụng” trong quan hệ thể/dụng có mục tiêu theo đuổi; tách concept dụng thần |
| `manh_phai.to_cong` | Sơ cấp 26–27 | Có trình tự xét can ngày rồi chi ngày; điều kiện ngữ cảnh không phải một quan hệ hợp là đủ kết luận |
| `manh_phai.ung_ky` | Cao cấp 6–7 | Tách nguyên cục/đại vận/lưu niên và dẫn động |
| `tu_binh.dung_than` | Tử Bình 26–30, chương 8 và các chú | Phải giữ sự khác nhau giữa nguyên văn và bình chú, không thu gọn toàn bộ Tử Bình thành một công thức |

Các mã concept trên là **đề xuất thiết kế**, không tuyên bố tác giả đã dùng đúng các ID đó. Các nội dung dự báo trong sách là ghi nhận của nguồn, không là bằng chứng y khoa/tài chính.

## Quy trình duyệt

State entity revision: `draft → in_review → approved | rejected`; approved có thể `revoked`, revision mới trở lại draft. Candidate extraction tạo draft và evidence, không có transition trực tiếp từ job sang approved. UI cho xem nguồn bên trái, candidate bên phải, diff revision, điều kiện/ngoại lệ và test cases. Reviewer phải kiểm chữ OCR, phạm vi trường phái, speaker, điều kiện, các exception, nguồn đối chiếu và wording.

Approve rule còn phải: DSL schema pass, paths/functions tồn tại, dependency DAG acyclic, không dùng arbitrary code, ít nhất positive/negative/missing-fact fixtures, all cited spans accepted và rights hợp lệ, reviewer ghi rationale. Approval ghi `reviews` append-only và audit event trong transaction. Không sửa approved row tại chỗ. Revoke không xóa historical trace; rule set kế tiếp loại nó; analysis bị đánh dấu stale/withdrawn theo lý do.

## Mệnh lệ

`case_revision` lưu ordered pillars year/month/day/hour có thể thiếu giờ; sex-for-luck nullable, birth_date nullable, source narrative, annotated outcomes, time windows, school/method, evidence, quality. Tứ trụ trong sách không đủ để suy ngược một ngày sinh duy nhất: không bịa ngày sinh. Có `origin=book_case|user_case|synthetic_test`; user_case private theo owner. Case events là lời kể của nguồn (`claimed_event`), không gọi đó là outcome đã xác minh độc lập.

Parser lấy block/table + narrative theo section, phát hiện hàng Can/Chi/Đại Vận; kiểm 60 pairs hợp lệ, 4 positions, Không/Unknown rõ ràng. Nếu reorder cột mơ hồ, đưa review. Cases approved dùng retrieval/evaluation; case revisions dùng làm gold không được dùng để tune cùng split. So khớp cấu trúc case chỉ hỗ trợ nghiên cứu, không chứng minh tương lai người dùng giống case.

## Impact analysis

Mọi analysis/message claim ghi `analysis_dependencies` tới chart/policy, corpus/chunk/page revision, ontology/term revision, assertion/rule revision, ruleset, prompt/model profile. Index `(dependency_kind, dependency_id)` phục vụ query impacted analyses. Sửa alias tạo ontology release mới, corpus release mới tái dùng generations/chunks hiện có và ghim ontology mới; ảnh hưởng retrieval policy version và các run dùng nó, không phải re-embed mọi document. Sửa school assignment/classification thì tạo generation classification mới để scope cũ không drift. Sửa rule tạo revision/ruleset mới, invalidate cache theo version, enqueue re-evaluation cho người có quyền. Lưu kết quả cũ + diff mới, không lặng lẽ viết lại lịch sử.

## Conflict và không xác định

Giữ cả luận cứ ủng hộ/phản đối nếu trường phái/method khác nhau. Trong một method, cặp output cùng claim_key nhưng value mâu thuẫn tạo conflict record, không cho priority tự xóa một bên. Priority chỉ sắp thứ tự kiểm tra; resolution phải là quy tắc ngoại lệ có nguồn đã duyệt hoặc reviewer chọn method rõ ràng. Không có nguồn/đủ điều kiện → `unknown/insufficient_evidence`, không ép true/false.

## Candidate example có nguồn, chưa phê duyệt

Từ sơ cấp PDF 26: candidate `manh_phai.to_cong.day_stem_first`, source layer là lời trình bày trong sách, source_explicit. Điều kiện structural có thể kiểm: vị trí can ngày có quan hệ hợp hoặc sinh với can khác; luận ý nghĩa của quan hệ vẫn cần xác định chủ thể/đối tượng, điều kiện và ngoại lệ từ đoạn 26–27. Không mã hóa thành `has_hop → giàu` vì nguồn không cho phép rút gọn vậy. Record lưu applicability có predicate xác định, interpretation_notes cần thẩm định, evidence span 26–27 và review_state=draft. Reviewer phải xác định method và fixtures trước khi rule usable. Đây minh họa ánh xạ từ sách sang model, không là quy tắc production đã duyệt.
