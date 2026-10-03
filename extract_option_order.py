#!/usr/bin/env python3
"""Match the latest up366 homework's choice questions to the option order the app saved.

The app stores the display order of a choice question under
`<element_id>_optionOrder` (via u3Client.saveData).  The value is an array of
original option indexes in display order, e.g. [2,0,1] means A = options[2],
B = options[0], C = options[1].  The same order is also printed to the app log
as `optionOrder:[...]` every time the question is rendered.  This script reads
those log blocks (read-only) and pairs them with the questions in page order.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_answers import (  # noqa: E402
    clean_html,
    find_latest_homework,
    iter_page_questions,
    load_page_config,
    page_files,
)
from option_order_lib import find_page_task_id, latest_orders_for_homework  # noqa: E402
from u3enc_tool import load_or_default_key  # noqa: E402

CHOICE_TYPES = (1, 108, 109)


def choice_questions(homework_dir, key):
    questions = []
    for page in page_files(homework_dir) or []:
        cfg = load_page_config(page, key)
        for section_title, sub in iter_page_questions(cfg):
            if not sub.get("options"):
                continue
            if sub.get("question_type") not in CHOICE_TYPES and sub.get("qtype_id") not in CHOICE_TYPES:
                continue
            questions.append({
                "question_id": sub.get("question_id", ""),
                "element_id": sub.get("element_id", ""),
                "section": section_title,
                "question_text": clean_html(sub.get("question_text", "")),
                "answer_text": clean_html(sub.get("answer_text", "")),
                "options": [(str(o.get("id", "")).strip(), clean_html(o.get("content", "")))
                           for o in (sub.get("options") or [])],
                "order": None,
            })
    return questions


def apply_order(question, order):
    options = question["options"]
    mapping = []
    for display_pos, orig_index in enumerate(order):
        if 0 <= orig_index < len(options):
            orig_id, content = options[orig_index]
        else:
            orig_id, content = "?", "?"
        mapping.append((chr(65 + display_pos), orig_id, content))
    question["order"] = order
    question["mapping"] = mapping


def format_report(homework_dir, page_task_id, questions, source):
    lines = []
    lines.append("=" * 70)
    lines.append("up366 最新作业 - 选择题选项交换信息")
    lines.append(f"作业目录: {homework_dir}")
    lines.append(f"作业UUID: {homework_dir.name}")
    lines.append(f"pageTaskId: {page_task_id}")
    lines.append(f"来源日志: {source}")
    lines.append("=" * 70)
    lines.append("说明: optionOrder 是原始选项下标在显示时的排列，")
    lines.append("例如 [2,0,1] 表示 A=原始第2项, B=原始第0项, C=原始第1项。")
    lines.append("answer_text 为原始选项编号，即标准答案。")
    lines.append("=" * 70)

    current_section = None
    for i, q in enumerate(questions, 1):
        if q["section"] != current_section:
            current_section = q["section"]
            lines.append("")
            lines.append("-" * 70)
            lines.append(f"【分类】{current_section or '未分类'}")
            lines.append("-" * 70)
        lines.append("")
        lines.append(f"{i}. 题目: {q['question_text'] or '(无题目文本)'}")
        lines.append(f"   question_id: {q['question_id']}")
        lines.append(f"   element_id: {q['element_id']}")
        lines.append("   原始选项:")
        for idx, (oid, content) in enumerate(q["options"]):
            lines.append(f"     [{idx}] {oid}. {content}")
        lines.append(f"   标准答案(原始): {q['answer_text'] or '?'}")
        if q.get("order") is not None:
            lines.append(f"   交换信息 optionOrder: {q['order']}")
            lines.append("   显示顺序:")
            for display_letter, orig_id, content in q.get("mapping", []):
                lines.append(f"     {display_letter} = 原始选项 [{q['order'][ord(display_letter) - 65]}] ({orig_id}) {content}")
            correct = next((letter for letter, oid, _ in q.get("mapping", []) if oid == q["answer_text"]), None)
            lines.append(f"   界面上应选: {correct or '(未知)'}")
        else:
            lines.append("   交换信息: 未在日志中找到（该题可能已作答/提交，按原始顺序显示）")

    lines.append("")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=r"D:\Up366StudentFiles",
                        help="up366 data root (default: D:\\Up366StudentFiles)")
    parser.add_argument("--exe", default=None,
                        help="path to up366.exe used to extract the AES key")
    parser.add_argument("--key-hex", default=None,
                        help="legacy 32-char hex AES key (current .u3enc files are auto-detected)")
    parser.add_argument("--output", default=None,
                        help="output txt path (default: workspace 最新作业选项顺序.txt)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    data_dir = Path(args.data_dir)
    exe = Path(args.exe) if args.exe else Path(__file__).resolve().with_name("up366.exe")
    key = load_or_default_key(exe, args.key_hex)

    homework_dir = find_latest_homework(data_dir)
    print(f"latest homework: {homework_dir}", file=sys.stderr)

    page_task_id = find_page_task_id(homework_dir, key)
    print(f"pageTaskId: {page_task_id}", file=sys.stderr)

    questions = choice_questions(homework_dir, key)
    print(f"choice questions: {len(questions)}", file=sys.stderr)

    source, orders = latest_orders_for_homework(data_dir / "logs", key, homework_dir)
    if orders:
        for q, order in zip(questions, orders):
            if q is not None:
                apply_order(q, order)
    source = source or "未找到匹配日志块"

    output = Path(args.output) if args.output else Path(__file__).resolve().parent / "最新作业选项顺序.txt"
    text = format_report(homework_dir, page_task_id, questions, source)
    output.write_text(text, encoding="utf-8-sig")
    print(f"wrote -> {output}")
    print(f"source: {source}", file=sys.stderr)


if __name__ == "__main__":
    main()
