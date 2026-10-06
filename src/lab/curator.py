"""GUIDE Phần 3 - Người tuyển chọn skill (skill curator): tự viết skill từ các lần chạy thất bại.   >>> SINH VIÊN CÀI ĐẶT curate_skills <<<

Pseudo-code: guides/pseudocode/04_curator.md
Kiểm tra:    pytest tests/test_04_curator.py
Chạy thật:   python -m lab.curator
"""
import json
import re
from pathlib import Path

from .tasks import eval_markers   # có sẵn: định danh của tác vụ đánh giá, tính lúc chạy

# ---- CÓ SẴN, KHÔNG SỬA: kiểm tra và tách khối skill (phần dễ sai và liên quan bảo mật) ----------------
SAFE_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def validate_skill(text: str, expected_name: str | None = None) -> list[str]:
    """Kiểm tra nội dung một SKILL.md. Trả về danh sách vấn đề (rỗng = hợp lệ).

    Quy tắc: có khối YAML frontmatter; `name` chữ thường/số/gạch ngang (tối đa 64 ký tự) và bằng `expected_name`
    nếu được truyền; có `description` (tối đa 1024 ký tự); phần thân tối đa 80 dòng; không chứa chuỗi nào của
    `eval_markers()`. Quy tắc về `name` cũng là biện pháp bảo mật: tên khối do LLM sinh ra được dùng để tạo
    đường dẫn, nên `../evil` không được lọt qua.
    """
    problems = []
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text.strip() + "\n", re.S)
    if not m:
        return ["missing YAML frontmatter"]
    front, body = m.groups()
    name = re.search(r"^name:\s*(.+)$", front, re.M)
    desc = re.search(r"^description:\s*(.+)$", front, re.M)
    n = name.group(1).strip() if name else ""
    if not SAFE_NAME.fullmatch(n) or len(n) > 64:
        problems.append("invalid name")
    elif expected_name is not None and n != expected_name:
        problems.append("name differs from the block name")
    if not desc or len(desc.group(1).strip()) > 1024:
        problems.append("missing or too long description")
    if len(body.strip().splitlines()) > 80:
        problems.append("body longer than 80 lines")
    low = text.lower()
    for marker in eval_markers():
        if marker in low:
            problems.append(f"mentions evaluation material: {marker}")
    return problems


def parse_skill_blocks(reply: str) -> list[tuple[str, str]]:
    """Tách câu trả lời của LLM thành danh sách (name, nội dung SKILL.md).

    Khuôn dạng: `=== SKILL: <name> ===` ... `=== END ===`. Một khối kết thúc ở điểm nào đến trước trong ba điểm:
    `=== END ===`, tiêu đề `=== SKILL:` kế tiếp, hoặc cuối văn bản (LLM đôi khi quên dòng END).
    """
    pattern = re.compile(r"^=== SKILL: (\S+) ===[ \t]*\n(.*?)(?=^=== END ===|^=== SKILL: |\Z)", re.S | re.M)
    return [(name, text.strip()) for name, text in pattern.findall(str(reply))]
# --------------------------------------------------------------------------------------------------


CURATOR_PROMPT = """You write SKILL files for an engineering agent that analyses code, data and logs.

Below are FAILED checks from LEARNING-task runs: the check name, the review bot's
feedback (the rule that was violated), and the end of the execution trace.

Find the PROCEDURAL mistakes that recur across runs - not the answers - and write at
most {max_skills} short skills that would prevent them on a NEW task of the same kind.

Rules:
- Be general. Never name a task id, a file that exists in only one task workspace, a
  function, a column, or any specific number. Write the procedure or the convention,
  not the instance.
- Each skill has YAML frontmatter with `name` (lower-case, digits and hyphens only)
  and `description` (ONE sentence starting with "Use when ..." that names the trigger
  situation and the broad task type), then at most 40 lines of imperative checklist.
- A skill may name an output file or key that the organisation's conventions require
  (for example answer.json, errors.json, clean.csv, a `meta` object, amounts as
  integer cents).

Output format, character for character:
=== SKILL: <name> ===
---
name: <name>
description: <when to use>
---
<content>
=== END ===

{runs}
"""


def curate_skills(results_dir="results", source_condition="baseline", out_dir=None, model=None, max_skills: int = 3) -> list[Path]:
    """Đọc các lần chạy của TÁC VỤ HỌC (role == "learn") trong `source_condition`, nhờ LLM viết skill, ghi file.

    Các bước: nạp run.json + trace.md -> (nếu không có check nào thất bại: in cảnh báo và trả về [] mà KHÔNG gọi LLM)
    -> dựng prompt -> model.invoke(prompt) -> parse_skill_blocks -> validate_skill(text, expected_name=name)
    -> ghi `<out_dir>/<name>/SKILL.md`. Mặc định `out_dir` = <gốc lab>/skills/auto (dùng `ROOT` từ lab.tasks).
    Giữ tối đa `max_skills` skill hợp lệ; skill không hợp lệ bị bỏ qua.
    Prompt chứa, với mỗi check thất bại, TÊN và trường `detail` (lời nhận xét của bot đánh giá: phát biểu quy tắc bị vi phạm)
    cùng phần cuối của vết (trace). Với tác vụ học, `detail` chỉ phát biểu quy tắc, không chứa đáp án.
    Tuyệt đối KHÔNG đưa dữ liệu của tác vụ đánh giá (role == "eval") vào prompt.
    model mặc định: make_model() (lab.model).
    Trả về: danh sách đường dẫn SKILL.md đã ghi.
    """
    from .model import make_model
    from .tasks import ROOT

    out_dir = Path(out_dir) if out_dir is not None else ROOT / "skills" / "auto"

    runs = []
    for p in sorted(Path(results_dir).glob(f"{source_condition}/*/run.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - run.json hỏng không được làm dừng việc tuyển chọn
            continue
        if r.get("role") != "learn":       # TUYỆT ĐỐI không dùng dữ liệu tác vụ đánh giá
            continue
        tp = p.parent / "trace.md"
        trace = tp.read_text(encoding="utf-8", errors="replace") if tp.exists() else ""
        failed = [
            {"name": c.get("name", "?"), "detail": str(c.get("detail") or "")}
            for c in r.get("checks", []) if not c.get("passed")
        ]
        runs.append({"task": r.get("task", p.parent.name), "failed": failed,
                     "trace": trace[-6000:]})

    # Không có check thất bại thì không gọi mô hình: không có gì để rút ra.
    if not any(r["failed"] for r in runs):
        print("WARNING: khong co check that bai o tac vu hoc - khong goi mo hinh, khong viet skill.")
        return []

    blocks = []
    for r in runs:
        lines = [f"### task: {r['task']}"]
        for f in r["failed"]:
            lines.append(f"- check that bai: {f['name']}")
            lines.append(f"  feedback: {f['detail']}")
        lines.append("trace (cuoi cung):")
        lines.append(r["trace"])
        blocks.append("\n".join(lines))

    # .replace() chứ không str.format(): prompt có nhiều dấu ngoặc JSON thật.
    prompt = CURATOR_PROMPT.replace("{max_skills}", str(max_skills)).replace("{runs}", "\n\n".join(blocks))

    m = model if model is not None else make_model()
    reply = str(m.invoke(prompt).content)

    written: list[Path] = []
    for name, text in parse_skill_blocks(reply):
        if len(written) >= max_skills:
            break
        problems = validate_skill(text, expected_name=name)
        if problems:
            print(f"bo qua skill {name!r}: {'; '.join(problems)}")
            continue
        d = out_dir / name
        d.mkdir(parents=True, exist_ok=True)
        sp = d / "SKILL.md"
        sp.write_text(text.rstrip() + "\n", encoding="utf-8")
        written.append(sp)
    return written


if __name__ == "__main__":
    for p in curate_skills():
        print("wrote", p)
