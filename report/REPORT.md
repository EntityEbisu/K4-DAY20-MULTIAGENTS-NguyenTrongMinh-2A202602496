# Báo cáo Lab: Self evolving Agentic

> Sao chép tệp này thành `report/REPORT.md` (đã làm ở Phần 0) và điền dần qua các Phần của lab. Xóa các dòng hướng dẫn dạng trích dẫn (bắt đầu bằng `>`). Văn phong kỹ thuật, ngắn gọn, mọi nhận định đi kèm số liệu hoặc bằng chứng. Trong buổi học: điền mục 1 đến 7 (bản nháp). Sau buổi học: hoàn thiện mục 8 đến 10.

## 1. Thông tin nhóm và cấu hình

| Họ tên | Mã sinh viên | Phần đóng góp |
|---|---|---|
| | | |

- Mô hình: `nvidia/nemotron-3-nano-4b` qua LM Studio Local Server (`http://host.docker.internal:1234/v1`); `LAB_TEMPERATURE=0`, context length 8192, `recursion_limit=40`.
- Phiên bản Deep Agents: `0.7.21`; máy chủ: Windows 11; agent chạy trong Docker Linux với Python 3.12.
- Số lần chạy tác vụ đã dùng / ngân sách:
- Commit của tag `freeze`:

## 2. Giả thuyết (commit TRƯỚC tag `freeze`, Phần 4.0)

> Dự đoán điều kiện nào đạt điểm cao nhất trên **tác vụ đánh giá** và vì sao. Nêu căn cứ từ phân loại lỗi (mục 4) và từ tài liệu tham khảo. Điền cả ba dòng; `verify_freeze.py` kiểm tra điều này.

- H1 (subagents so với baseline):
- H2 (skills-auto so với baseline):
- H3 (tác vụ học so với tác vụ đánh giá):

## 3. Làm quen Deep Agents (Phần 0.3)

1. Mô hình mặc định thấy các công cụ tệp `ls`, `read_file`, `write_file`, `edit_file`, `delete`, `glob`, `grep`; công cụ chạy lệnh là `execute`; công cụ giao việc cho subagent là `task`.
2. Subagent `general-purpose` có toàn bộ công cụ như tác tử chính. Mỗi lần gọi mặc định stateless; subagent chỉ thấy prompt được giao và trả về một báo cáo cuối.
3. System prompt mặc định rỗng (`''`). Mô tả `task`: “Each invocation is stateless by default: the agent sees only the prompt you give it and returns a single final report.” Mô tả `execute`: “You MUST avoid using search commands like find and grep. Instead use the grep, glob tools to search.”

## 4. Đường cơ sở và phân loại lỗi (Phần 2.2)

> Chỉ dùng tác vụ học. Mỗi dòng là một check thất bại.

| Tác vụ | Check thất bại | Nhóm lỗi (A-G) | Bằng chứng (trích ngắn từ `detail` hoặc vết) |
|---|---|---|---|
| code-learn | `parse_price_all_formats` | D | `wrong for: ['$1,299.50', '(12.00)', '$1,000,000.00']` — bỏ sót các định dạng giá được kiểm tra. |
| code-learn | `other_caller_fixed` | C | `to_csv_row returned '<InvalidOperation>'` — sửa parser nhưng caller dùng chung vẫn lỗi. |
| code-learn | `low_stock_follows_docstring` | A | `low_stock returned ['b', 'A', 'c']` — kết quả trái với quy ước trong docstring. |
| code-learn | `csv_quoting_follows_docstring` | A | `to_csv_row returned 'Desk, large "oak",10.00,2'` — không tuân theo định dạng CSV trong docstring. |
| code-learn | `rule_type_hints` | E | `RULE: every public function ... has type annotations ...` — check quy ước Acme. |
| data-learn | `north_q1_revenue` | B | `FileNotFoundError .../workspace/answer.json`; trace kết thúc sau lỗi `SyntaxError` khi chạy script, không có lần kiểm chứng/sửa tiếp theo. |
| data-learn | `rule_clean_csv` | E | `RULE: write workspace/clean.csv ...` — check quy ước đầu ra Acme. |
| logs-learn | `valid_structure` | A | `FileNotFoundError .../workspace/errors.json` — không tạo tệp đầu ra được yêu cầu. |

Nhận xét: thất bại trải trên việc bỏ sót đặc tả và định dạng (A, D), sửa chưa triệt để (C), không kiểm chứng sau lỗi (B), cùng các quy ước tổ chức (E). `check_breakdown.py` ghi nhận chỉ 1/18 check kỹ thuật và 0/9 check quy ước đạt; không có bằng chứng cho thấy kỹ năng tổng quát đã giúp được baseline.


## 5. Điều kiện `subagents` (Phần 2.3)

- Các subagent đã định nghĩa: `explorer` (đọc đề, README, docstring và báo cáo sự thật; không sửa), `implementer` (thực hiện thay đổi đã được đặc tả và tự kiểm tra), `reviewer` (đối chiếu độc lập từng yêu cầu; không sửa).
- `subagent_calls`: `code-learn=0`, `data-learn=0`, `logs-learn=0`. Trace của cả ba lần chạy không có lệnh gọi `task`; đây là kết quả hợp lệ. Tác tử chính đã làm trực tiếp, nên không có báo cáo subagent để đánh giá.
- Thông tin khi giao việc: không có giao việc; vì vậy không thể nhận xét về tính đầy đủ của prompt giao việc.
- Chi phí: baseline trung bình 48,850 token và 65.0 s/run; subagents trung bình 54,749 token và 101.7 s/run (+12.1% token, +56.5% thời gian). Subagent không được gọi, nhưng chế độ vẫn tốn hơn, nhất là do độ dài các lần chạy.


## 6. Self-evolving: skill do curator sinh (Phần 3)

- Số lần chạy curator, số skill bị xóa và lý do:

| Skill | Tổng quát hay riêng cho tác vụ học? | Đúng hay sai (nêu chỗ sai nếu có) | Độ dài, `description` và `skills_read` ở Phần 3.4 |
|---|---|---|---|
| | | | |

## 7. Kết quả so sánh (Phần 4.3, 4.4)

> Dán nội dung `report/table.md` và kết quả `python scripts/check_breakdown.py`. Nêu các lần chạy có `error` hoặc `skills_modified = true` (nếu có) và cách xử lý.

```text
(dán bảng ở đây)
```

## 8. Phân tích

> Trả lời từng câu bằng số liệu từ mục 7 và bằng chứng từ vết. Kết quả âm hoặc không có khác biệt vẫn hợp lệ nếu được phân tích tốt.

1. So với `baseline`, điều kiện nào cải thiện điểm tác vụ **học**? Điều kiện nào cải thiện điểm tác vụ **đánh giá**? Có điều kiện nào cải thiện tác vụ học nhưng không cải thiện tác vụ đánh giá? Nếu có, đó là dấu hiệu gì?
2. Tách điểm thành check kỹ thuật và check quy ước (`rule_`). Skill do curator sinh giúp nhóm check nào? Check quy ước **mới** của tác vụ đánh giá có được skill giúp không, và vì sao?
3. Dựa vào vết và `skills_read`, giải thích một check mà skill giúp đạt và một check mà skill không giúp (skill chưa được đọc, đọc nhưng không làm theo, skill thiếu hoặc sai).
4. Chi phí: so sánh số token trung bình giữa các điều kiện. Điều kiện nào có hiệu quả tốt nhất theo điểm trên mỗi token? Đa tác tử có đáng chi phí trong thí nghiệm này không?
5. Có dấu hiệu rò rỉ dữ liệu hoặc quá khớp nào trong skill sinh ra không? Nhóm đã phòng tránh như thế nào?
6. Nhiễu: so sánh điểm tác vụ học của cùng bộ skill ở Phần 3.4 (đã sao lưu) và sau đóng băng. Chênh lệch bao nhiêu? Nó cho biết điều gì về độ tin cậy của các chênh lệch trong bảng ở mục 7?

## 9. Hạn chế và tính hợp lệ

> Nêu ít nhất 3 hạn chế và ảnh hưởng của từng hạn chế đến kết luận (ví dụ: chỉ 3 tác vụ mỗi vai trò, mỗi cấu hình chạy một lần, nhiễu của mô hình, tác vụ do giảng viên thiết kế sẵn quy ước, chỉ một mô hình).

1.
2.
3.

## 10. Kết luận

> Tối đa 5 câu. Chỉ khẳng định điều số liệu hỗ trợ. Nêu một đề xuất cải tiến tiếp theo.

## Phụ lục

- Lệnh đã chạy (theo thứ tự):
- Thử thách mở rộng (nếu có): hướng chọn, kết quả, nhận xét.
- Ghi chú khác:
