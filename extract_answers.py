#!/usr/bin/env python3
"""Extract all answers from the newest up366 homework into a formatted txt file.

For choice questions the app shuffles option positions and stores the display
order locally plus in the app log as `<element_id>_optionOrder`.  This script
recovers that order from `D:\\Up366StudentFiles\\logs` (read-only) and prints,
in addition to the standard answer, the letter to click on screen.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from option_order_lib import latest_orders_for_homework  # noqa: E402
from u3enc_tool import decrypt_u3enc, extract_key  # noqa: E402

UUID_RE = re.compile(r'^[0-9A-Fa-f]{32}$')
PAGE_RE = re.compile(r'^page(\d+)\.js\.u3enc$', re.IGNORECASE)
HTML_TAG_RE = re.compile(r'<[^>]+>')

CHOICE_TYPES = (1, 108, 109)

TYPE_LABELS = {
    1: '选择题',
    2: '填空题',
    3: '判断题',
    4: '连线题',
    5: '简答题',
    6: '听力题',
    9: '朗读题',
    12: '口语回答',
    99: '听力组题',
}

QTYPE_LABELS = {
    108: '选择题',
    109: '选择题',
    531: '口语回答',
    532: '听后转述',
    583: '听后记录信息',
    588: '朗读题',
}


def clean_html(text):
    if not text:
        return ''
    text = html.unescape(str(text))
    text = HTML_TAG_RE.sub('', text)
    text = re.sub(r'[ \t\f\v]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    return text.strip()


def find_latest_homework(data_dir):
    flipbooks = data_dir / 'flipbooks'
    if not flipbooks.is_dir():
        raise FileNotFoundError(f'not found: {flipbooks}')

    candidates = []
    for book in flipbooks.iterdir():
        if not book.is_dir() or not UUID_RE.match(book.name):
            continue
        for hw in book.iterdir():
            if hw.is_dir() and UUID_RE.match(hw.name):
                candidates.append((hw.stat().st_mtime, hw.name, hw))

    if not candidates:
        raise FileNotFoundError('no homework folder (32-hex uuid) found under flipbooks')

    return max(candidates)[2]

def homework_dirs(data_dir):
    flipbooks = data_dir / 'flipbooks'
    if not flipbooks.is_dir():
        return []

    result = []
    for book in flipbooks.iterdir():
        if not book.is_dir() or not UUID_RE.match(book.name):
            continue
        for hw in book.iterdir():
            if hw.is_dir() and UUID_RE.match(hw.name):
                result.append((hw.stat().st_mtime, hw.name, book.name, hw))

    result.sort(key=lambda row: row[0], reverse=True)
    return result


def find_homework_by_uuid(data_dir, uuid):
    target = str(uuid).strip().lower()
    for _, hw_uuid, _, hw_dir in homework_dirs(data_dir):
        if hw_uuid.lower() == target:
            return hw_dir
    raise FileNotFoundError(f'homework {uuid} not found under {data_dir / "flipbooks"}')




def page_files(homework_dir):
    pages = []
    for p in homework_dir.glob('page*.js.u3enc'):
        m = PAGE_RE.match(p.name)
        if m:
            pages.append((int(m.group(1)), p))
    if pages:
        return [p for _, p in sorted(pages)]
    return None


def question_data_files(homework_dir):
    qdir = homework_dir / 'questions'
    if not qdir.is_dir():
        return []
    return sorted(
        (p for p in qdir.glob('*/questionData.js.u3enc') if UUID_RE.match(p.parent.name)),
        key=lambda p: p.parent.name,
    )


def load_page_config(path, key):
    data = decrypt_u3enc(path.read_bytes(), key)
    text = data.decode('utf-8-sig')
    if text.startswith('var pageConfig='):
        text = text[len('var pageConfig='):]
    return json.loads(text)


def option_text(item):
    options = item.get('options') or []
    result = []
    for opt in options:
        opt_id = str(opt.get('id', '')).strip()
        content = clean_html(opt.get('content', ''))
        if content:
            result.append((opt_id, content))
    return result


def answer_parts(item):
    answers = []
    qtype_id = item.get('qtype_id')
    if qtype_id == 532:
        ans = first_retell_answer(item)
        return [ans] if ans else []
    if qtype_id == 531:
        ans = longest_spoken_answer(item)
        return [ans] if ans else []
    answer_text = clean_html(item.get('answer_text', ''))
    if answer_text:
        for opt_id, content in option_text(item):
            if opt_id and answer_text.upper() == opt_id.upper():
                answers.append(f'{opt_id}（{content}）' if content else opt_id)
                break
        else:
            answers.append(answer_text)

    answers_list = item.get('answers_list') or []
    for entry in answers_list:
        content = clean_html(entry.get('content', ''))
        if content:
            answers.append(f"{entry.get('id', '?')}. {content}")

    record_speak = item.get('record_speak') or []
    for i, ref in enumerate(record_speak, 1):
        content = clean_html(ref.get('content', ''))
        if content:
            answers.append(f'{i}. {content}')

    if not answers:
        analysis = clean_html(item.get('analysis', ''))
        if analysis:
            answers.append(f'参考答案/朗读文本：{analysis}')

    return answers

RETEL_ANSWER_RE = re.compile(r'参考答案\s*[一二三四五六七八九十百]+\s*[：:]')

def first_retell_answer(item):
    analysis = clean_html(item.get('analysis', ''))
    parts = RETEL_ANSWER_RE.split(analysis)
    candidates = [part.strip() for part in parts if part.strip()]
    if candidates:
        return candidates[0]
    for ref in item.get('record_speak') or []:
        content = clean_html(ref.get('content', ''))
        if content:
            return content
    return ''

def longest_spoken_answer(item):
    candidates = [
        clean_html(ref.get('content', ''))
        for ref in item.get('record_speak') or []
    ]
    candidates = [content for content in candidates if content]
    if not candidates:
        return ''
    return max(candidates, key=len)



def type_label(item):
    qtype_id = item.get('qtype_id')
    if qtype_id in QTYPE_LABELS:
        return QTYPE_LABELS[qtype_id]
    return TYPE_LABELS.get(item.get('question_type'), f'qtype {qtype_id or "?"}')


def is_choice(item):
    return item.get('question_type') in CHOICE_TYPES or item.get('qtype_id') in CHOICE_TYPES


def display_options(item):
    order = item.get('option_order')
    if not order:
        return None
    ids = item.get('option_ids') or []
    options = dict(item.get('options') or [])
    result = []
    for display_pos, orig_index in enumerate(order):
        if 0 <= orig_index < len(ids):
            oid = ids[orig_index]
            content = options.get(oid, '')
        else:
            oid, content = '?', '?'
        result.append((chr(65 + display_pos), oid, content))
    return result


def display_answers(item):
    order = item.get('option_order')
    answer_text = (item.get('answer_text') or '').strip().upper()
    if not order or not answer_text:
        return None
    ids = item.get('option_ids') or []
    orig_to_display = {}
    for display_pos, orig_index in enumerate(order):
        if 0 <= orig_index < len(ids):
            orig_to_display[ids[orig_index].upper()] = chr(65 + display_pos)

    mapped = []
    for token in re.split(r'[,\s、，]+', answer_text):
        if not token:
            continue
        if len(token) == 1:
            mapped.append(orig_to_display.get(token, ''))
        else:
            mapped.extend(orig_to_display.get(ch, '') for ch in token)
    mapped = [m for m in mapped if m]
    return mapped or None

def choice_display_answers(item):
    order = item.get('option_order')
    answer_text = (item.get('answer_text') or '').strip().upper()
    options = dict(item.get('options') or [])
    ids = item.get('option_ids') or []
    if not answer_text:
        return None

    result = []
    if order:
        orig_to_display = {}
        for display_pos, orig_index in enumerate(order):
            if 0 <= orig_index < len(ids):
                orig_to_display[ids[orig_index].upper()] = chr(65 + display_pos)
        for token in re.split(r'[,\s、，]+', answer_text):
            if not token:
                continue
            for ch in token:
                display = orig_to_display.get(ch, '')
                if not display:
                    continue
                content = options.get(ch, '')
                result.append(f'{display}（{content}）' if content else display)
    else:
        for opt_id, content in item.get('options') or []:
            if opt_id.upper() == answer_text:
                result.append(f'{opt_id}（{content}）' if content else opt_id)
                break
        else:
            result.append(answer_text)

    return result or None



def make_item(slide, section_title):
    raw_options = slide.get('options') or []
    answers_list = slide.get('answers_list') or []
    item = {
        'section': section_title,
        'question_text': clean_html(slide.get('question_text', '')),
        'knowledge': clean_html(slide.get('knowledge', '')),
        'score': slide.get('question_score', ''),
        'options': option_text(slide),
        'option_ids': [str(o.get('id', '')).strip() for o in raw_options],
        'answers': answer_parts(slide),
        'fill_answers': [clean_html(entry.get('content', '')) for entry in answers_list if clean_html(entry.get('content', ''))],
        'analysis': clean_html(slide.get('analysis', '')),
        'question_id': slide.get('question_id', ''),
        'element_id': slide.get('element_id', ''),
        'question_type': slide.get('question_type'),
        'qtype_id': slide.get('qtype_id'),
        'answer_text': clean_html(slide.get('answer_text', '')),
        'type': type_label(slide),
        'option_order': None,
        'display_options': None,
        'display_answers': None,
    }
    return item


def collect_items(homework_dir, key):
    pages = page_files(homework_dir)
    items = []

    if pages is not None:
        for page in pages:
            cfg = load_page_config(page, key)
            for section in cfg.get('sections', []):
                section_title = clean_html(section.get('sectionTitle', ''))
                for slide in section.get('slides', []):
                    sub_list = slide.get('questions_list') or []
                    if sub_list:
                        for sub in sub_list:
                            items.append(make_item(sub, section_title))
                    else:
                        items.append(make_item(slide, section_title))
    else:
        for qd in question_data_files(homework_dir):
            cfg = load_page_config(qd, key)
            items.append(make_item(cfg.get('questionObj', cfg), '未分类'))

    return items


def apply_option_orders(items, homework_dir, key, data_dir):
    source, orders = latest_orders_for_homework(data_dir / 'logs', key, homework_dir)
    if orders:
        choice_items = [it for it in items if is_choice(it)]
        for item, order in zip(choice_items, orders):
            item['option_order'] = list(order)
        for item in items:
            if item.get('option_order') is not None:
                item['display_options'] = display_options(item)
                item['display_answers'] = display_answers(item)
    return source or '未找到匹配日志块'

def build_answer_text(data_dir, homework_dir, key):
    items = collect_items(homework_dir, key)
    order_source = apply_option_orders(items, homework_dir, key, data_dir)
    return format_items(items, homework_dir, order_source), items



def format_items(items, homework_dir, order_source):
    lines = []
    lines.append('=' * 70)
    lines.append('up366 最新作业答案')
    lines.append(f'作业目录: {homework_dir}')
    lines.append(f'作业UUID: {homework_dir.name}')
    lines.append(f'题目总数: {len(items)}')
    lines.append(f'选项交换信息来源: {order_source}')
    lines.append('=' * 70)

    current_section = None
    for i, item in enumerate(items, 1):
        if item['section'] != current_section:
            current_section = item['section']
            lines.append('')
            lines.append('-' * 70)
            lines.append(f'【分类】{current_section or "未分类"}')
            lines.append('-' * 70)

        lines.append('')
        title = item['question_text'] or '(无题目文本)'
        meta = [f'{i}.', f"[{item['type']}]"]
        if item['knowledge']:
            meta.append(f"知识点: {item['knowledge']}")
        if item['score']:
            meta.append(f"{item['score']}分")
        lines.append(' '.join(meta))
        lines.append(f'题目: {title}')

        if item['display_options']:
            lines.append('界面选项(按当前交换顺序):')
            for letter, orig_id, content in item['display_options']:
                if content:
                    lines.append(f'  {letter}. {content}')
                else:
                    lines.append(f'  {letter}. ({orig_id})')

        lines.append('答案:')
        display_answers_list = choice_display_answers(item) if is_choice(item) else None
        answers = display_answers_list if display_answers_list is not None else item['answers']
        if answers:
            for ans in answers:
                lines.append(f'  {ans}')
        else:
            lines.append('  (该题未提供标准答案)')



    lines.append('')
    return '\n'.join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Extract all answers from the newest up366 homework to a txt file'
    )
    parser.add_argument('--data-dir', default=r'D:\Up366StudentFiles',
                        help='up366 data root (default: D:\\Up366StudentFiles)')
    parser.add_argument('--exe', default=None,
                        help='path to up366.exe used to extract the AES key')
    parser.add_argument('--output', default=None,
                        help='output txt path (default: workspace 最新作业答案.txt)')
    parser.add_argument('--homework-uuid', default=None,
                        help='32-hex homework UUID to parse (default: latest)')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    data_dir = Path(args.data_dir)
    exe = Path(args.exe) if args.exe else Path(__file__).resolve().with_name('up366.exe')
    output = Path(args.output) if args.output else Path(__file__).resolve().parent / '最新作业答案.txt'

    _, key, _ = extract_key(exe)
    if args.homework_uuid:
        homework_dir = find_homework_by_uuid(data_dir, args.homework_uuid)
    else:
        homework_dir = find_latest_homework(data_dir)
    print(f'homework: {homework_dir}', file=sys.stderr)

    text, items = build_answer_text(data_dir, homework_dir, key)

    output.write_text(text, encoding='utf-8-sig')
    print(f'wrote {len(items)} answers -> {output}')


if __name__ == '__main__':
    main()
