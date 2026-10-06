# Báo cáo Lab: Self evolving Agentic

## 1. Thông tin nhóm và cấu hình

| Họ tên | Mã sinh viên | Phần đóng góp |
|---|---|---|
| Nguyen Trong Minh | 02496 | Cài đặt harness, chạy thí nghiệm, phân tích và báo cáo |

- Mô hình: `nvidia/nemotron-3-nano-4b` (Q4_K_M), LM Studio Local Server; `LAB_TEMPERATURE=0`, context đang nạp 8.192 token (giới hạn model hiển thị 1.048.576), `recursion_limit=40`. `lms ps --json` xác nhận model đang được nạp và trạng thái phục vụ yêu cầu.
- Đường kết nối: tệp cấu hình LM Studio trỏ tới `http://127.0.0.1:1234/v1`; `.env` của repo dùng `http://host.docker.internal:1234/v1` để container gọi host. Đã so sánh key và model giữa hai tệp bằng phép so sánh trong bộ nhớ, không in bí mật; cả hai khớp. `make_model()` đọc `.env` và tạo `ChatOpenAI`; một completion thật từ container trả về phản hồi. Docker image không chứa biến cấu hình API; `.env` được mount cùng repo và bị Git ignore.
- Deep Agents `0.7.21`; host Windows 11; agent chạy trong Docker Linux với Python 3.12.15.
- Kết quả được giữ: 18 bản ghi condition/task cuối (bốn bản ghi là retry), 4 lần thử lỗi đầu tiên đã lưu riêng, và 3 bản ghi `skills-auto-dev` trước freeze; curator được gọi 3 lần. Số request API chính xác không có trong `run.json` (chỉ có token/công cụ tổng hợp), ngân sách môn học không được cung cấp. Hai lệnh học `skills-auto` ban đầu cùng ghi vào một thư mục; chỉ bộ kết quả được sao lưu cuối cùng còn kiểm chứng được.
- Commit `hypotheses`: `411651d`; commit/tag `freeze`: `0fb92df`.

## 2. Giả thuyết (commit TRƯỚC tag `freeze`, Phần 4.0)

- H1 (subagents so với baseline): Trên tập đánh giá, `subagents` dự kiến không cải thiện điểm so với `baseline`, và có thể giảm hiệu quả điểm/token. Ở tác vụ học, mô hình không gọi `task` lần nào trong ba lần chạy; trung bình tốn thêm 12.1% token và 56.5% thời gian mà không có subagent thực sự tham gia.
- H2 (skills-auto so với baseline): Với cấu hình thực tế này, dự kiến `skills-auto` không cải thiện điểm: curator đã được gọi ba lần nhưng không sinh skill hợp lệ, nên thư mục skill rỗng; bản thân thêm ghi chú/nạp skill có thể còn làm đầy cửa sổ ngữ cảnh 8K. SkillsBench báo lợi ích trung bình cho skill được biên soạn và kiểm soát (33.9% lên 50.5%, +16.6 điểm phần trăm), nhưng đó không phải bằng chứng cho skill tự sinh.[1] SkillEvolBench báo các agent hiện thường không hình thành được skill bền vững và lợi ích trên acquisition không ổn định khi triển khai trên task đã đóng băng.[2]
- H3 (tác vụ học so với tác vụ đánh giá): Điểm trên `eval` dự kiến không cao hơn `learn`, vì mỗi task đánh giá giữ lại loại công việc nhưng bổ sung một quy ước tổ chức mới không có trong task học (GUIDE §2.2); đồng thời baseline hiện chưa hoàn thành được đầu ra kỹ thuật cơ bản.


## 3. Làm quen Deep Agents (Phần 0.3)

1. Mô hình mặc định thấy các công cụ tệp `ls`, `read_file`, `write_file`, `edit_file`, `delete`, `glob`, `grep`; công cụ chạy lệnh là `execute`; công cụ giao việc cho subagent là `task`.
2. Subagent `general-purpose` có toàn bộ công cụ như tác tử chính. Mỗi lần gọi mặc định stateless; subagent chỉ thấy prompt được giao và trả về một báo cáo cuối.
3. System prompt mặc định rỗng (`''`). Mô tả `task`: “Each invocation is stateless by default: the agent sees only the prompt you give it and returns a single final report.” Mô tả `execute`: “You MUST avoid using search commands like find and grep. Instead use the grep, glob tools to search.”

## 4. Đường cơ sở và phân loại lỗi (Phần 2.2)

Bảng dùng kết quả `baseline` trên ba tác vụ học lần đầu. Trace `code-learn` lần đầu được bảo toàn tại `results/attempts-before-retry/baseline/code-learn/`.

| Tác vụ | Check thất bại | Nhóm lỗi | Bằng chứng |
|---|---|---|---|
| code-learn | `visible_suite_passes` | G | `2 failed, 4 passed`; trace gọi `cd /workspace` nhưng nhận `can't cd`, sau đó pytest báo không tìm thấy `tests/`. |
| code-learn | `parse_price_all_formats` | G | `wrong for: ['$1,299.50', '(12.00)', '$1,000,000.00']`; trace đã đọc docstring nhưng không sửa được mã. |
| code-learn | `other_caller_fixed` | G | `to_csv_row returned '<InvalidOperation>'`; trace thử import bằng cú pháp sai và không chạy được kiểm thử hợp lệ. |
| code-learn | `discount_rounds_half_up` | G | Ba trường hợp làm tròn sai; trace mắc kẹt ở đường dẫn và chạy lệnh kiểm tra, không triển khai sửa đổi. |
| code-learn | `low_stock_follows_docstring` | G | `low_stock returned ['A','b','c']`; docstring yêu cầu sắp xếp không phân biệt hoa thường, nhưng không có sửa đổi. |
| code-learn | `csv_quoting_follows_docstring` | G | `to_csv_row returned 'Desk, large "oak",10.00,2'`; trace đã đọc quy tắc RFC 4180 nhưng không sửa hàm. |
| code-learn | `rule_type_hints` | E | `RULE: every public function ... has type annotations`. |
| code-learn | `rule_regression_tests` | E | `RULE: add tests/test_regressions.py ... (at least 3)`. |
| code-learn | `rule_changelog` | E | `RULE: record each fix in CHANGELOG.md ... (at least 3 bullets)`. |
| data-learn | `north_q1_revenue` | B | `FileNotFoundError: answer.json`; trace dừng sau `SyntaxError: unterminated string literal` trong script tính toán. |
| data-learn | `north_q1_orders` | B | `FileNotFoundError: answer.json`; cùng lỗi script và không có lần chạy sửa/kiểm chứng sau đó. |
| data-learn | `top_region` | B | `FileNotFoundError: answer.json`; không có kết quả tính được ghi ra. |
| data-learn | `missing_amount_orders` | B | `FileNotFoundError: answer.json`; trace kết thúc trước khi có đầu ra. |
| data-learn | `duplicate_rows_removed` | B | `FileNotFoundError: answer.json`; trace kết thúc sau lỗi cú pháp. |
| data-learn | `rule_money_in_cents` | E | Check `rule_`; `answer.json` không tồn tại nên không có giá trị để kiểm tra. |
| data-learn | `rule_meta_block` | E | Check `rule_`; `answer.json` không tồn tại nên không có khối `meta` để kiểm tra. |
| data-learn | `rule_clean_csv` | E | `RULE: write workspace/clean.csv ...`; tệp đầu ra không được tạo. |
| logs-learn | `valid_structure` | B | `FileNotFoundError: errors.json`; trace chỉ đọc trang đầu của log rồi kết thúc mà không ghi đầu ra. |
| logs-learn | `entry_count` | B | `FileNotFoundError: errors.json`; không có tệp để đối chiếu số entry. |
| logs-learn | `timestamps_utc` | B | `FileNotFoundError: errors.json`; không có tệp để kiểm tra timestamp. |
| logs-learn | `exception_fields` | B | `FileNotFoundError: errors.json`; không có tệp để kiểm tra exception. |
| logs-learn | `repeat_counts` | B | `FileNotFoundError: errors.json`; không có tệp để kiểm tra số lần lặp. |
| logs-learn | `counts_by_service` | B | `FileNotFoundError: errors.json`; không có tệp để tổng hợp theo service. |
| logs-learn | `rule_service_names` | E | Check `rule_`; `errors.json` không tồn tại. |
| logs-learn | `rule_sorted_errors` | E | Check `rule_`; `errors.json` không tồn tại. |
| logs-learn | `rule_schema_header` | E | Check `rule_`; `errors.json` không tồn tại. |

Nhóm B xuất hiện ở 11 check, E ở 9, G ở 6. Với code-learn, trace cho thấy agent đã đọc docstring; lỗi chính không phải bỏ qua đặc tả mà là không xử lý được đường dẫn shell/tool và không tạo thay đổi. `check_breakdown.py` xác nhận chỉ 1/18 check kỹ thuật và 0/9 check quy ước đạt ở baseline learning. Một skill về đường dẫn tương đối/kiểm chứng có thể là giả thuyết cải thiện, nhưng curator không tạo được skill để kiểm tra giả thuyết đó.


## 5. Điều kiện `subagents` (Phần 2.3)

- Các subagent đã định nghĩa: `explorer` (được gọi đầu tiên để đọc đề/README/docstring/dữ liệu và báo cáo, không sửa), `implementer` (được gọi khi đã rõ thay đổi; nhận đủ đường dẫn/quy tắc, sửa và tự kiểm tra), `reviewer` (được gọi sau sửa đổi để kiểm tra độc lập, không sửa). Ba vai trò có phạm vi và system prompt riêng.
- `subagent_calls` ở tác vụ học: `code-learn=0`, `data-learn=0`, `logs-learn=0`; trace không có lệnh `task`. Đây là kết quả hợp lệ; tác tử chính làm trực tiếp. Không có báo cáo subagent để đánh giá độ đầy đủ.
- So với baseline learning, subagents dùng trung bình 54.749 token và 101,7 s/run so với 48.851 token và 65,0 s/run: +12,1% token và +56,5% thời gian. Không có giao việc thực tế nên không thể quy khác biệt này cho phối hợp đa tác tử.


## 6. Self-evolving: skill do curator sinh (Phần 3)

- Curator được gọi 3 lần (lần đầu + 2 lần chạy lại được phép); 0 skill được parser chấp nhận; 0 skill bị xóa; không chỉnh tay `skills/auto/`. Thư mục chỉ có `.gitkeep` và `README.md`.

| Skill | Tổng quát hay riêng cho tác vụ học? | Đúng hay sai | Độ dài, `description` và `skills_read` |
|---|---|---|---|
| Không có | Không áp dụng | Cả ba phản hồi đều không chứa khối `=== SKILL: ... ===` nên `parse_skill_blocks` trả về rỗng. Phản hồi cuối vẫn tiếp tục suy luận về dữ liệu log (`We need to compute for each error/CRITICAL entry`) thay vì xuất skill. | Không có `SKILL.md` nên độ dài/`description` không áp dụng. `skills_read=0` ở cả sáu run `skills-auto` chính thức và cả ba run học trước freeze. |

Nguyên nhân đã đo, không phải phỏng đoán: prompt curator dựng từ ba run học baseline dài khoảng 20.754 ký tự (khoảng 5.200 đến 5.800 token, chủ yếu là 3 × 6.000 ký tự trace cuối cùng), trong khi LM Studio đang nạp model với context 8.192 token. Model này còn sinh token suy luận (`reasoning`), và một probe 8 token đã cho thấy toàn bộ ngân sách bị dùng cho phần suy luận. Vì vậy phần ngân sách còn lại không đủ để model viết hết khối skill theo định dạng yêu cầu; đây là giới hạn ngân sách ngữ cảnh của cấu hình, không phải lỗi trong `curate_skills`. Không có skill nào được tạo, nên nhóm không thể đánh giá chất lượng skill và không có cơ sở để nói về quá khớp hay rò rỉ ở tầng skill.


## 7. Kết quả so sánh (Phần 4.3, 4.4)

Bảng do `python -m lab.compare` sinh từ 18 kết quả condition/task cuối cùng; bốn task từng gặp `GraphRecursionError` đã chạy lại sau khi sao lưu lần đầu.

```text
| Task | baseline | subagents | skills-auto |
|---|---|---|---|
| code-learn | 1/10 | 1/10 | 2/10 |
| data-learn | 0/8 | 1/8 | 0/8 |
| logs-learn | 0/9 | 0/9 | 0/9 |
| code-eval | 2/11 | 4/11 | 3/11 |
| data-eval | 0/9 | 0/9 | 0/9 |
| logs-eval | 0/10 | 0/10 | 0/10 |
| **Mean score - learning tasks** | 0.03 | 0.07 | 0.07 |
| **Mean score - evaluation tasks** | 0.06 | 0.12 | 0.09 |
| **Mean tokens per run** | 50,316 | 61,081 | 47,261 |
| **Runs that read a skill** | 0/6 | 0/6 | 0/6 |
```

`python scripts/check_breakdown.py`:

```text
condition     role    technical  house rules  mean tokens  read a skill
baseline      eval      2/18         0/12          56,221      0/3
baseline      learn     1/18         0/9           44,410      0/3
subagents     eval      4/18         0/12          69,685      0/3
subagents     learn     2/18         0/9           52,477      0/3
skills-auto   eval      3/18         0/12          51,260      0/3
skills-auto   learn     2/18         0/9           43,262      0/3
```

Không còn run chính thức nào có `error`; các bốn lần đầu lỗi recursion được giữ tại `results/attempts-before-retry/`. Retry code-eval baseline đổi từ 4/11 xuống 2/11, cho thấy biến thiên đáng kể. Không run nào có `skills_modified=true` hoặc `skills_read>0`; sáu run skills-auto phát cảnh báo không tìm thấy thư mục `/skills/` vì không có skill hợp lệ. Ba run `skills-auto-dev` trước freeze được giữ riêng; hai run code/data gặp API context-size error nên không thay thế bằng chứng cho một lần chạy thành công.



## 8. Phân tích

1. Điểm trung bình learning cuối cùng là baseline `0,03`, subagents `0,07`, skills-auto `0,07`; điểm evaluation lần lượt `0,06`, `0,12`, `0,09`. Vì vậy H1 và H2 không được ủng hộ bởi bảng điểm: subagents và skills-auto cao hơn baseline trên eval; H3 cũng không được ủng hộ vì điểm eval cao hơn learning ở cả ba điều kiện. Tuy nhiên, eval tăng chủ yếu ở họ code; data/logs đều 0 điểm, và không có lần gọi subagent hay đọc skill, nên không thể quy chênh lệch cho hai cơ chế đó.
2. `check_breakdown.py` cho eval: kỹ thuật đạt baseline `2/18`, subagents `4/18`, skills-auto `3/18`; check quy ước đạt `0/12` ở cả ba. Không skill nào được sinh/đọc; các quy ước mới ở eval (`rule_version_bump`, `rule_sorted_keys_format`, `rule_source_line`) đều trượt. Kết quả cho thấy không có bằng chứng skill hỗ trợ nhóm check nào.
3. Không thể nêu một check được skill giúp vì `skills_read=0` trong cả 18 run và `skills/auto/` không có `SKILL.md`. Ví dụ skills-auto/code-eval đạt `billable_blocks_round_up` và `negative_minutes_rejected`, nhưng run không đọc skill nên đây là hành vi của agent/model, không phải hiệu quả của skill. `rule_version_bump` vẫn trượt; với thư viện rỗng, không thể kết luận một skill bị đọc nhưng không làm theo.
4. Token trung bình/run: baseline `50.316`, subagents `61.081` (+21,4% so với baseline), skills-auto `47.261`; thời gian trung bình lần lượt `100,1`, `122,9`, `67,1` giây. Theo hiệu quả eval được tính là tổng điểm task dạng tỷ lệ chia tổng token rồi nhân 1.000.000, các mức là baseline `1,08`, subagents `1,74`, skills-auto `1,77` điểm-tỷ-lệ/triệu token. Dù skills-auto cao nhất theo chỉ số này, không có skill nào được dùng; còn subagents đắt hơn nhưng `subagent_calls=0` ở cả sáu run. Thí nghiệm không cho thấy lợi ích phối hợp đa tác tử.
5. Không thấy bằng chứng rò rỉ hay quá khớp trong skill vì không có skill được tạo; do đó đây là câu hỏi chưa thể kiểm tra, không phải bằng chứng rủi ro bằng 0. Quy trình giữ eval ngoài dữ liệu curator, commit H1-H3 trước tag `freeze`, không sửa `skills/auto/`, và `verify_freeze.py` xác nhận sáu run dùng đúng hash đã đóng băng.
6. Trước freeze, skills-auto-dev đạt `1/10`, `0/8`, `0/9` (mean score `0,033`); hai run code/data bị `Context size has been exceeded`, mỗi run `0` token. Sau freeze, cùng thư viện rỗng đạt `2/10`, `0/8`, `0/9` (mean `0,067`), tức thêm một check trong 27 check tổng. Vì hai lần trước không sinh được phản hồi mô hình, chênh lệch này không phải ước lượng nhiễu thuần. Một dấu hiệu biến thiên khác: baseline/code-eval lần đầu `4/11` với recursion error, lần chạy lại `2/11` không lỗi; các so sánh đơn lần cần được xem thận trọng.


## 9. Hạn chế và tính hợp lệ

1. Chỉ ba họ task và một canonical result cho mỗi condition/task; không có ước lượng tin cậy hay khoảng dao động ổn định. Baseline/code-eval đổi từ 4/11 ở lần đầu lỗi sang 2/11 khi chạy lại.
2. Chỉ một cấu hình: Nemotron 3 Nano 4B Q4_K_M, context LM Studio 8.192, temperature 0, recursion limit 40. Hai run skills-auto trước freeze bị context overflow; kết luận không suy rộng sang model hoặc context khác.
3. Curator không tạo skill hợp lệ vì prompt (~5.200 đến 5.800 token) cộng token suy luận vượt ngân sách khả dụng của context 8.192; `skills-auto` vì vậy chạy với thư mục skill rỗng. Hệ quả: không thể kết luận gì về lợi ích hay quá khớp của skill tự sinh, và hạng mục đánh giá skill của lab không có dữ liệu.
4. `subagent_calls=0` ở các run; điều kiện `subagents` không thực sự kiểm tra phối hợp nhiều tác tử.
5. Bốn lần đầu có recursion error đã được retry và lưu riêng; hai run development context-error cũng được giữ. Hai lần gọi skills-auto learning đầu dùng chung thư mục output nên chỉ bộ kết quả còn lại được kiểm chứng; số request API chính xác không có trong metadata. Những hạn chế này làm giảm độ tin cậy của so sánh dù freeze gate đạt.

## 10. Kết luận

Trong 18 bản ghi cuối, điểm eval trung bình là baseline 0,06, subagents 0,12 và skills-auto 0,09, nhưng cả ba điều kiện đều đạt 0/12 check quy ước và họ data/logs không đạt check nào. Vì không run nào gọi `task` hay đọc skill, chênh lệch điểm không chứng minh lợi ích của đa tác tử hay self-evolution. Curator không tạo được skill vì prompt khoảng 5.200 đến 5.800 token gặp context 8.192 token, và model tiêu hết phần ngân sách còn lại cho suy luận. Retry baseline `code-eval` đổi từ 4/11 xuống 2/11, nên một lần chạy cho mỗi ô không đủ để kết luận ổn định. Bước tiếp theo là tăng context LM Studio hoặc rút gọn trace gửi curator, rồi lặp mỗi điều kiện ít nhất ba lần trong thư mục kết quả riêng.

## Phụ lục

### Lệnh đã chạy (theo thứ tự)

Trên Windows, mọi lệnh `python`/`pytest` của lab được chạy trong Docker:
`docker run --rm -v "$PWD:/lab" -w /lab lab-day20 <lệnh>`.

```bash
pytest tests/test_01_provided.py
python scripts/tour.py
pytest tests/test_02_agent.py -k subagents
pytest tests/test_02_agent.py
pytest tests/test_03_runner.py
pytest tests/test_04_curator.py
python -m lab.runner --condition baseline --tasks learn --recursion-limit 40
python -m lab.runner --condition subagents --tasks learn --recursion-limit 40
python -m lab.curator
mv results/skills-auto results/skills-auto-dev      # sao lưu kết quả Phần 3.4
python -m lab.runner --condition skills-auto --tasks learn --recursion-limit 40
git commit -m "hypotheses"
git commit --allow-empty -m "freeze skills" && git tag freeze
python -m lab.runner --condition baseline --tasks eval --recursion-limit 40
python -m lab.runner --condition subagents --tasks eval --recursion-limit 40
python -m lab.runner --condition skills-auto --tasks all --recursion-limit 40
python scripts/verify_freeze.py
python -m lab.compare > report/table.md
python scripts/check_breakdown.py
pytest
```

Bốn task gặp `GraphRecursionError` ở lần chạy đầu (`baseline/code-learn`, `baseline/code-eval`, `subagents/code-learn`, `skills-auto/data-learn`) đã được sao lưu vào `results/attempts-before-retry/` rồi chạy lại riêng bằng `--tasks <id>` với cùng `--recursion-limit 40`.

### Thử thách mở rộng

Không thực hiện. Hướng khả thi nhất là 6e (lặp để đo nhiễu), nhưng chưa làm được vì hai lý do đã nêu ở mục 9: curator không sinh được skill nên hướng 6a/6b không có đối tượng để so sánh, và mỗi lần lặp tốn thêm token/thời gian.

### Ghi chú khác

- Suy luận cục bộ: mô hình `nvidia/nemotron-3-nano-4b` (Q4_K_M) chạy qua LM Studio Local Server trên máy host, container kết nối bằng `host.docker.internal:1234/v1`. Khóa API nằm trong `.env` (đã bị Git ignore, không commit) và không xuất hiện trong mã nguồn, trace hay báo cáo.
- `make_model()` trong `src/lab/model.py` là tệp có sẵn, không sửa; lab dùng nhánh Azure/OpenAI-compatible của hàm này.
- `tools/lmstudio_shim.py` là proxy tương thích tạo cho thử nghiệm Ternary-Bonsai trước đó; các lần chạy Nemotron trong báo cáo không dùng shim.
- Các lần chạy pilot với mô hình khác nằm ở `results/pilot-ternary/` và `results/pilot-nemotron/`; chúng không được tính vào bảng so sánh chính thức.
- `skills/auto/` chỉ chứa `.gitkeep` và `README.md`; không có `SKILL.md` nào được ghi trong suốt quá trình làm lab.


## Sources

[1] https://arxiv.org/abs/2602.12670
[2] https://arxiv.org/abs/2605.24117
