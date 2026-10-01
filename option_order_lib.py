#!/usr/bin/env python3
"""Shared helpers for reading up366 logs and recovering saved choice-option orders."""

import gzip
import re
from pathlib import Path

from u3enc_tool import decrypt_u3enc

TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
PAGE_TASK_ID_RE = re.compile(r"pageTaskId\s*=\s*'([0-9a-fA-F]{32})'", re.IGNORECASE)
TASK_FIELD_RE = re.compile(r'"task_id"\s*:\s*"([0-9a-fA-F]{32})"')
RANDOM_BLOCK_RE = re.compile(r"\[JSLog\] random_ques_arrIndex:")
OPTION_ORDER_RE = re.compile(r"\[JSLog\] optionOrder:\[([^\]]*)\]")
TASK_ID_RE = re.compile(r'"taskid":"([0-9a-fA-F]{32})"')


def read_log_text(log_dir):
    entries = []
    for path in sorted(Path(log_dir).glob("app.log*")):
        try:
            if path.suffix == ".gz":
                text = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        entries.append((path.name, text))
    return entries


def task_blocks(entries, page_task_id):
    """Return (log_name, start_line, block_text) blocks belonging to this task."""
    result = []
    for log_name, text in entries:
        lines = text.splitlines()
        markers = [i for i, line in enumerate(lines) if RANDOM_BLOCK_RE.search(line)]
        for pos, start in enumerate(markers):
            end = markers[pos + 1] if pos + 1 < len(markers) else len(lines)
            block = "\n".join(lines[start:end])
            context = "\n".join(lines[max(0, start - 80):start])
            m = TASK_ID_RE.search(context + "\n" + block)
            if page_task_id and m and m.group(1).lower() == page_task_id:
                result.append((log_name, start, block))
    return result


def parse_orders(block):
    orders = []
    for m in OPTION_ORDER_RE.finditer(block):
        parts = [int(x) for x in m.group(1).split(",") if x.strip() != ""]
        if parts:
            orders.append(parts)
    return orders


def find_page_task_id(homework_dir, key):
    path = Path(homework_dir)

    # Legacy layout: pageTaskId lives in the homework HTML.
    html_enc = next(path.glob("*.html.u3enc"), None)
    if html_enc is not None:
        try:
            plain = decrypt_u3enc(html_enc.read_bytes(), key).decode("utf-8", "replace")
        except Exception:
            plain = ""
        m = PAGE_TASK_ID_RE.search(plain)
        if m:
            return m.group(1).lower()

    # Current layout (client >= 6.13.0): page1.js exposes taskObj.task_id.
    for page in sorted(path.glob("page*.js.u3enc")):
        try:
            plain = decrypt_u3enc(page.read_bytes(), key).decode("utf-8-sig", "replace")
        except Exception:
            continue
        m = TASK_FIELD_RE.search(plain)
        if m:
            return m.group(1).lower()
    return None


def latest_orders_for_homework(log_dir, key, homework_dir):
    """Return (source_desc, orders) for the most recent render of this homework."""
    page_task_id = find_page_task_id(homework_dir, key)
    if not page_task_id:
        return None, None
    entries = read_log_text(log_dir)
    blocks = task_blocks(entries, page_task_id)
    if not blocks:
        return None, None

    def block_ts(block):
        m = TS_RE.search(block)
        return m.group(1) if m else ""

    blocks.sort(key=lambda b: block_ts(b[2]))
    for log_name, start_line, block in reversed(blocks):
        orders = parse_orders(block)
        if orders:
            return f"{log_name} (行 {start_line})", orders
    return None, None
