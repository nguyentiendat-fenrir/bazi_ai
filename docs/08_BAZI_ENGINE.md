# 08 · Calculation Engine và Rule Engine

## A. Calculation Engine

### Tái sử dụng có điều kiện

Giữ tables/functions và `lunar-python` qua adapter. Tách `calendar_adapter`, `time_normalizer`, `pillars`, `ten_gods`, `hidden_stems`, `relations`, `luck_cycles`, `policy_registry`. `legacy/bazi` immutable dùng tái hiện. Không dùng payload tiếng Việt cũ làm public contract mới; mapping một lần tại adapter. Adapter phải ghi `legacy_version`, package version, tzdata version, astronomical model và policy hash.

### BirthInput contract

```json
{
  "calendar_system": "gregorian",
  "local_datetime": "2000-06-15T05:30:00",
  "timezone": "Asia/Ho_Chi_Minh",
  "fold": null,
  "longitude": null,
  "latitude": null,
  "sex_for_luck": "male",
  "time_accuracy": "minute",
  "uncertainty_minutes": 0,
  "policy_id": "standard-v1"
}
```

Ngày trong ví dụ là dữ liệu tổng hợp. `local_datetime` không offset vì là wall clock; offset/UTC được server tính từ IANA timezone. API **từ chối** offset trong trường này để tránh hai nguồn sự thật. Nếu lịch âm: thay local_datetime bằng `lunar_date:{year,month,day,is_leap_month}` và `local_time`, cùng calendar_system; hai dạng input loại trừ nhau. Calendar không được hỗ trợ trả 422, không fallback.

sex_for_luck=`male|female|unspecified`: là tham số thuật toán thuận/nghịch, không suy từ tên. `unspecified` vẫn lập bốn trụ nhưng các vận phụ thuộc giới tính trả unknown, hoặc user yêu cầu hai biến thể. Longitude trong [-180,180], latitude [-90,90]; apparent_solar bắt buộc longitude, latitude là metadata không bị giả dùng vào EOT. `time_accuracy=unknown` không giả giờ 12:00: trả ba trụ và hour=null, vận có thể partial. Khoảng bất định giao ranh giới giờ/ngày/tiết sinh nhiều biến thể với bounds và lý do.

### Chính sách thời gian

1. Parse/validate civil date, không gọi `.astimezone()` trên naive datetime. Gắn IANA + fold, round-trip UTC để phát hiện nonexistent time; DST gap từ chối và giải thích. DST fold phải chọn 0/1 nếu mơ hồ. Cùng input test dưới host TZ UTC/Asia/Ho_Chi_Minh/America/New_York phải cùng chart hash.
2. Canonical `birth_instant_utc` là physical instant. Giờ dùng tính trụ ngày/giờ lưu riêng `pillar_clock_local`. Không cộng EOT rồi đổi nghĩa physical instant; không áp correction hai lần.
3. Tiết khí là instant thiên văn toàn cầu. Thư viện trả thời gian dân sự theo chuẩn của nó thì adapter chuyển chuẩn đó về UTC trước so sánh, không lấy giờ UTC+8 làm giờ Việt. Năm đổi tại Lập Xuân; tháng đổi tại 12 tiết, không theo ngày mồng 1 âm lịch. So sánh instant và nêu tolerance nguồn oracle.
4. Mặc định `day_rollover=midnight`; lựa chọn `zi_start_23` là policy khác. Thuật toán can giờ phải nhất quán theo day policy được công bố, đặc biệt 23:00–00:00. Không chỉ gọi setSect rồi mặc định tất cả phương thức thư viện cùng chuyển.
5. `clock_basis=civil|apparent_solar`. Apparent solar áp dụng EOT có version + kinh độ + offset lịch sử; DST được xử lý một lần. Công thức tham chiếu NOAA là kiểm tra xấp xỉ, không coi nó là ephemeris độ chính xác tuyệt đối. Chọn implementation và sai số qua T027/T029, hiển thị uncertainty khi sát ranh giới.
6. `yun_method=traditional_units|minute_units` tương ứng phương pháp được kiểm chứng, không nhập nhằng với day sect. Year polarity và sex_for_luck quyết định direction theo policy. Khoảng tới tiết tính bằng physical instants; không dùng giờ Mặt Trời đã chỉnh như timestamp UTC.

### ChartFacts schema v1

`chart_id, schema_version, input_snapshot, normalized_time, policy_snapshot, engine_manifest, facts_hash, computed_at, warnings, variants`.

`normalized_time`: birth_instant_utc, civil_local, pillar_clock_local, utc_offset_seconds, fold, eot_minutes nullable, longitude_correction_minutes nullable, previous_jie/next_jie `{key,instant_utc,source_version}`.

`pillars`: object year/month/day/hour; mỗi pillar `{stem:"jia",branch:"chen",stem_label:"Giáp",branch_label:"Thìn",stem_element:"wood",ten_god:"peer",hidden_stems:[{stem,rank,ten_god}],growth_stage,na_yin,void}`; hour nullable nếu chưa biết giờ. Enums IDs ASCII ổn định, label Việt tại presentation layer. Canonical stem IDs: jia,yi,bing,ding,wu,ji,geng,xin,ren,gui; branch IDs: zi,chou,yin,mao,chen,si,wu,wei,shen,you,xu,hai. Hai `wu` nằm trong namespace stem/branch riêng, không so string đơn lẻ ngoài type.

`relations`: `{type,positions,members,completeness,conditions_evaluated}`. Hai thành viên tam hợp không tự thành full combination; tách `partial_combination`. Có positions để biết trùng chi; không mất multiplicity do convert set. Hợp/hình/xung là quan hệ tính được, không đồng nghĩa đã hóa hoặc xảy ra sự kiện đời sống.

`cycles`: `{direction,start_age_components,start_instant,start_method,da_yun:[{index,start,end,stem,branch}],liu_nian:[{solar_term_year,start_instant,end_instant,stem,branch}]}`. Khoảng `[start,end)` theo Lập Xuân cho Lưu Niên. Tuổi thực/tuổi mụ label riêng; không ghi “năm dương 2024” tương đương cả năm Quý Mão. Năm đầu trước Lập Xuân là interval phần năm, không lùi toàn bộ chuỗi 100 năm.

`auxiliary`: ming_gong,tai_yuan,element_counts; heuristic_weighted_scores mang method/version và `interpretation_ready=false` mặc định. Chỉ field có căn cứ/đã verify mới nằm trong allowed Rule facts. `warnings`: unsupported range, approximate_time, boundary_uncertainty, pending_auxiliary_validation. Nếu core pillars không qua gate không trả “verified”; có thể preview experimental nhưng không dùng production rule analysis.

### Oracle và audit gates

Tập 1900–2100, đặc biệt 12 tiết ±1s/±1m/±1h, Lập Xuân trước/sau tại UTC+7/+8, Tý 22:59/23:00/23:59/00:00/00:01, DST gap/fold, timezone lịch sử Việt Nam, leap day, leap lunar month, longitude ±180, uncertainty crossing boundary. Đối chiếu HKO solar-term tables + implementation thiên văn độc lập được ghi version, lịch/tzdata IANA và bảng mệnh lý chuyên gia duyệt. sxtwl và lunar-python có thể cùng họ thuật toán, không tính là hai oracle độc lập hoàn toàn. Oracle chưa giải quyết → test BLOCKED, không ghi pass.

Đã triển khai (T026–T028, `backend/app/calc/`, thuần, không DB/mạng/giờ máy): `timebase` (BirthInput `extra=forbid`; wall clock không offset; IANA lấy **chỉ** từ gói `tzdata` pin, không dùng bản của hệ điều hành; DST gap → `NONEXISTENT_TIME`, fold thiếu → `AMBIGUOUS_TIME`; giờ Mặt Trời biểu kiến = instant UTC + 4′×kinh độ + EOT NOAA, áp một lần từ instant vật lý), `solar_terms` (tiết khí sxwnl của lunar-python đổi từ giờ Bắc Kinh UTC+8 sang UTC một lần; so sánh instant), `pillars` (năm đổi tại instant Lập Xuân, tháng tại 12 tiết + ngũ hổ độn, ngày theo số ngày Julian của đồng hồ trụ, giờ 2 tiếng + ngũ thử độn; 23:00–24:00 luôn là giờ Tý của ngày hôm sau, `zi23-v1` thì chuyển cả trụ ngày lúc 23:00), `tables` (tàng can 3 khí, 12 trường sinh theo nhật chủ, nạp âm id ASCII + nhãn Việt, không vong theo tuần của trụ ngày), `relations` (ngũ hợp/xung can, lục hợp/xung/hại/phá/hình/tự hình, tam hợp/tam hội full|partial, bán hợp có chi chính; giữ positions và multiplicity; `conditions_evaluated=false`), `lunar` (`lunar_cn` theo lunar-python, `lunar_vn` theo thuật toán Hồ Ngọc Đức UTC+7: Tết 1985 = 21/01, 2007 = 17/02, 1968 = 29/01), `chart.compute` (ChartFacts đủ trường + `facts_hash` SHA-256 JSON chuẩn, không gồm chart_id/computed_at). Policies: `standard-v1` (civil, nửa đêm), `zi23-v1`, `solar-time-v1` (cần kinh độ); `policy_snapshot` + `policy_hash` lưu trong facts. Giờ không biết hoặc khoảng ± phút: cắt khoảng tại mọi tiết/ranh ngày/ranh giờ; trụ đổi trong khoảng thì null + `variants` có bounds và lý do (không giả 12:00); vận khi đó chỉ có `start_range_utc`. Đại vận: chiều theo âm dương can năm × `sex_for_luck` (`unspecified` → không lập + cảnh báo); `traditional_units` = ngày lịch + chênh canh giờ trong giờ dân sự nơi sinh (3 ngày = 1 năm, 1 ngày = 4 tháng, 1 canh = 10 ngày), `minute_units` = phút chẵn; mốc khởi vận cộng trên lịch dân sự nơi sinh. Lưu niên theo khoảng `[Lập Xuân, Lập Xuân)`, năm đầu chỉ phần sau giờ sinh. Cảnh báo: `near_solar_term` (≤120 s tới tiết), `historical_offset` (Asia/Ho_Chi_Minh 1942–1975 khác +7: miền Bắc dùng Asia/Bangkok), `boundary_uncertainty`, `approximate_time`, `luck_direction_unknown`, `pending_auxiliary_validation` (mệnh cung/thai nguyên theo công thức legacy, không là rule fact).

Đã kiểm (T029, `tests/unit/test_calc_engine.py`, `test_calc_oracle.py`): mọi tiết khí 1900–2100 (4.824) so với PyEphem/VSOP87 (kinh độ biểu kiến địa tâm, không chung mã với sxwnl): trung vị 9,5 s, lớn nhất 57 s (ΔT ngoại suy sau 2025) — dung sai 60 s; tứ trụ + tuổi khởi vận + đại vận khớp lunar-python ở UTC+8 cố định (400 lá số ngẫu nhiên × 2 phương pháp, 0 lệch); Lập Xuân ±1 s/±1 phút/±1 giờ ở UTC+7/+8, Tý 22:59/23:00/23:59/00:00/00:01 cho hai policy, DST gap/fold, múi giờ lịch sử VN, 29/02, tháng nhuận âm, kinh độ ±180, khoảng bất định qua ranh giới, cùng `facts_hash` khi đổi TZ máy; 32 lá số hồi quy đóng băng. Chưa có: bảng HKO (cần dữ liệu ngoài), chuyên gia duyệt policy/bảng mệnh lý — T029 vẫn ⏳ phần đó.

### Dữ kiện từ lá số viết sẵn (`calc/pillar_facts.py`)

Câu hỏi có thể chứa sẵn tứ trụ và đại vận dạng chữ ("Lá số nam: Mậu Ngọ – Ất Mão – Nhâm Tý – Canh Tý. Đại vận: …"). `find_chart` đọc tứ trụ, đại vận (chỉ chuỗi liền nhau sau "Đại vận", cho phép tuổi/năm trong ngoặc) và giới tính; `facts` tính bằng bảng tra, không dùng lịch hay LLM:

- B1 Nhật chủ (can ngày), B2 Nguyệt lệnh (chi tháng, chủ khí và thập thần của nó);
- thập thần của can, tàng can theo thứ tự chủ khí → trung khí → dư khí, vòng trường sinh của Nhật chủ tại mỗi chi;
- Lộc (Lâm quan), Kình Dương (Đế vượng, chỉ can dương), Thiên Mã truyền thống theo chi năm và chi ngày;
- quan hệ trong tứ trụ và giữa từng đại vận với tứ trụ: ngũ hợp, can xung, lục hợp/xung/hại/phá, hình, tự hình, tam hợp (đủ/bán hợp/củng), tam hội, tam hình, ám hợp (MPSC tr.179), tự hợp và chi hợp khắc can (DOCX ¶200–202); khung đủ ba chi ghi rõ "đã đủ trong tứ trụ" hay "đủ nhờ vận";
- cảnh báo khi lá số không thể có (cặp can chi sai âm dương, can tháng sai Ngũ Hổ độn, can giờ sai Ngũ Thử độn, đại vận không nối tiếp trụ tháng hoặc sai chiều theo giới tính).

Hợp chỉ ghi là hợp, không bao giờ ghi hóa. `render` xuất khối tiếng Việt cho prompt, mở đầu bằng nhãn "tính bằng bảng tra, không phải trích sách" để không bị coi là nguồn trích dẫn.

## B. Rule Engine độc lập LLM

### DSL contract v1

JSON có `$schema_version`, `rule_key`, `school_id`, `method_id`, `fact_schema_version`, `when`, `unless` (optional), `requires` (rule revision IDs), `emits`, `evidence_ids`, `explanation_template`, `limits`. DSL school_id/method_id dùng stable registry keys (như manh_phai), service resolve và kiểm khớp FK UUID school/method trên knowledge_rules; không xem key string là UUID. Lifecycle/review nằm DB, không tin `approved=true` trong JSON do client gửi.

```json
{
  "$schema_version": "bazi-rule/1",
  "rule_key": "synthetic.wood_day_master",
  "school_id": "test_only",
  "method_id": "structural_fixture",
  "fact_schema_version": "chart-facts/1",
  "when": {"op":"eq","left":{"fact":"pillars.day.stem_element"},"right":{"literal":"wood"}},
  "requires": [],
  "emits": [{"claim_key":"fixture.day_element","value":"wood","kind":"structural"}],
  "evidence_ids": [],
  "explanation_template": "Nhật can thuộc Mộc theo dữ kiện tính toán.",
  "limits": {"max_nodes":256}
}
```

Ví dụ trên là **fixture kỹ thuật, không là rule mệnh lý đã duyệt**, không được seed vào production active ruleset. Rule mệnh lý production bắt buộc evidence nguồn + reviewer; facts structural có nguồn thuật toán test fixture riêng, không giả citation sách.

### AST và hàm cho phép

Expr là một trong `{literal: scalar|array}`, `{fact: registered_path}`, `{op: operator, ...}` hoặc `{call: function_id,args:[Expr]}`. Không JSONPath tùy ý, attribute dunder, import, network, file IO, vòng lặp, regex tùy ý, Python/SQL. Operators cố định: `eq/ne/gt/gte/lt/lte/in/contains/all/any/not/exists`. `all/any` nhận `args` expressions, `not` nhận arg, comparisons nhận left/right; type checker chặn so stem với branch hay string với number. Null không bằng “không tồn tại”.

Function allowlist typed: `has_relation(type,positions,completeness)`, `hidden_stem_contains(position,stem)`, `ten_god_of(stem,day_stem)`, `count_branch(branch)`, `cycle_at(instant,type)`, `rule_fired(rule_revision_id)`. Function registry versioned, hàm thuần và deterministic; chỉ đọc facts snapshot đã validate. Không có hàm “đoán tài vận” không định nghĩa.

### Evaluation semantics

Tri-valued T/F/U. Thiếu hour → phép so trên hour là U; `not U=U`, `all` có F thì F, không F mà có U thì U; `any` có T thì T, không T mà có U thì U. `when=T` và `unless=F/absent` mới fired; `unless=T` blocked_exception; `unless=U` pending; `requires` tất cả fired, nếu dependency unknown thì pending. Không biến unknown thành false rồi kích hoạt quy tắc phủ định.

Validate DAG khi approve/ruleset build, reject cycles và references khác school nếu không có bridge được duyệt. Topological order + revision ID làm tie-break đảm bảo deterministic. Priority chỉ ordering, không cho rule tùy tiện đè kết luận. Limits mặc định depth≤16, nodes≤256/rule, ≤5.000 rules/run, ≤100.000 node evals/run, timeout CPU 2s cần benchmark; exceeded trả `resource_limit`, giữ partial trace nhưng không tuyên bố full analysis.

Đã triển khai (T022, `backend/app/rules/`): `facts.py` là registry `chart-facts/1` (stem/branch/stem_element/ten_god/growth_stage/na_yin/void của bốn trụ, `cycles.direction`; enum ID ASCII, `wu` stem ≠ `wu` branch) và bảng thập thần thuần; `dsl.py` kiểm schema (khóa bắt buộc, không khóa lạ, school/method là key registry), AST (literal/fact/op/call, toán tử và hàm trong allowlist, đúng số đối), kiểu (literal mang kiểu của vế kia và phải thuộc enum đó; không so stem với branch, chuỗi với số; gt/lt chỉ cho số), giới hạn ≤ 256 node, sâu ≤ 16; đánh giá ba trị đúng semantics trên cho một rule trên một facts snapshot (`count_branch` là U khi còn trụ chưa biết, `rule_fired` là U khi không có ngữ cảnh). Chạy cả ruleset, trace, DAG toàn cục và giới hạn mỗi run là T031. `cycle_at(instant, cycle_type)` có từ T031: trả `"stem-branch"` của đại vận/lưu niên chạy tại instant (fact `query.as_of` do yêu cầu phân tích cấp, kiểu `instant`); trước vận đầu, sau vận cuối hoặc khi mốc vận bất định → U.

Đã triển khai (T031–T034): `rules/engine.py` chạy cả ruleset trên một facts snapshot — thứ tự topo theo `requires` (revision id), hòa thì theo ordinal rồi id; thiếu dependency → `DEPENDENCY_MISSING`, vòng → `RULE_CYCLE`; dependency pending → pending, dependency không fired → `dependency_blocked`; ngân sách mỗi run (≤5.000 rule, ≤100.000 node, 2 s CPU) hết thì `resource_limit`, giữ trace đã có, phần còn lại `skipped`, không tuyên bố phân tích đầy đủ. Trace mỗi rule: status, when/unless, trạng thái dependency, mọi fact đã đọc và giá trị, evidence, claim phát ra, số node. Claim cùng key khác value → conflict mang mọi nguồn, không gộp. Duyệt rule (T033) thêm: dependency phải cùng school/method (chưa có cầu nối). Ruleset: `POST /rulesets` chụp các revision đã duyệt (mặc định revision mới nhất của mỗi rule), kiểm DAG, đóng băng manifest (DB chặn thành viên chưa duyệt/khác phương pháp); `POST /rulesets/{id}/activate` là compare-and-swap, ruleset cũ retired và mọi analysis dùng nó stale (`ruleset_superseded`). `POST /charts/{id}/analyses` (202, xong ngay vì chưa có phần LLM) chạy ruleset active trên facts bất biến của lá số (+ `as_of`), lưu claims/conflicts, `rule_traces` từng rule (status DB true/false/unknown/conflict/skipped, chi tiết trong predicates) và `analysis_dependencies` (ruleset, mọi revision thành viên, lá số + facts_hash). Thu hồi một rule (T034) → analysis phụ thuộc stale, ruleset chứa nó bị từ chối (`RULESET_HAS_REVOKED_RULE`) cho tới khi kích hoạt ruleset mới; trace cũ vẫn hiện rule đã thu hồi. `POST /analyses/{id}/reevaluate` chạy facts cũ với ruleset active hiện tại, tạo analysis mới và diff claims (thêm/bỏ/giữ). Rule mệnh lý thật vẫn cần chuyên gia duyệt (T033 phần nội dung).

Trace mỗi rule: revision_id, status (`fired/not_matched/pending/blocked_exception/dependency_blocked`), evaluated predicates với fact values, exception results, dependencies, source evidence, emitted claim keys, runtime counters. Trace là bằng chứng kiểm tra điều kiện, không yêu cầu lưu chain-of-thought riêng tư của LLM.

### Conflict và hybrid interpretation

Output claim_key typed cùng target+school+method+time_scope; hai values loại trừ tạo conflict và trả cả source. Không gộp Manh và Tử Bình chung trace. Các khái niệm cần phán đoán như cách cục, hiệu suất tố công, vượng nhược chỉ tạo `interpretation_candidate` nếu phần điều kiện xác định đúng, sau đó RAG+LLM diễn giải có nhãn suy luận và nguồn. LLM không ghi kết luận đó ngược thành chart fact hoặc approved rule.

Rule update → ruleset revision mới; `analysis_dependencies` tìm impacted results, re-evaluation chạy facts snapshot cũ với ruleset mới và ghi diff. Revocation thay current ruleset, lịch sử vẫn hiện “quy tắc đã thu hồi” và không tái dùng kết luận đó như bằng chứng mới.
