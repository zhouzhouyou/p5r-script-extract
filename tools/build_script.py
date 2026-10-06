#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a readable Persona 5 Royal (Chinese) dialogue script from .msg files
decompiled by Atlus Script Tools.

Outputs (relative to the workspace root):
  P5R_对话脚本\00_总目录.md        index of every emitted file + counts
  P5R_对话脚本\<category>\*.txt    readable dialogue per source file
  _staging\                         intermediate decompiled .msg (not a deliverable)
"""

import os
import re
import sys
import collections

# Paths are derived from this file's location so the tools work from any checkout:
#   <root>/tools/build_script.py  ->  <root>/_staging/decompiled, <root>/P5R_对话脚本
# Override with the P5R_ROOT environment variable if needed.
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('P5R_ROOT') or os.path.dirname(_HERE)

STAGING = os.path.join(ROOT, '_staging', 'decompiled')
OUTPUT = os.path.join(ROOT, 'P5R_对话脚本')
INDEX_NAME = '00_总目录.md'

# --------------------------------------------------------------------------
# .msg parsing
# --------------------------------------------------------------------------

MSG_HEADER = re.compile(r'^\[msg\s+(.*)$')
SEL_HEADER = re.compile(r'^\[sel\s+(.*)$')
SPEAKER_RE = re.compile(r'^(?P<name>.*?)\s*\[(?P<speaker>[^\[\]]*)\]$', re.S)

DROP_TAGS = {'clr', 'bup', 'f', 'vp', 'w', 'e', 'n', 'b', 'v', 'x', 's',
             'sel', 'msg', 'ref', 'dlg', 'we', 'nwe', 'cut'}
NEWLINE_TAGS = {'n', 'nwe'}

ESC_OPEN = '\x00O\x00'
ESC_CLOSE = '\x00C\x00'


def esc(text):
    return text.replace('\\[', ESC_OPEN).replace('\\]', ESC_CLOSE)


def unesc(text):
    return text.replace(ESC_OPEN, '[').replace(ESC_CLOSE, ']')

def clean_name(name):
    """The decompiler can emit stray ']' characters when an identifier is not a
    valid C identifier (it wraps such names in double backticks). Strip the
    leftovers so the speaker tag stays detectable."""
    n = name.strip()
    while n.endswith(']'):
        n = n[:-1].rstrip()
    return n.strip().strip('`').strip()


def strip_speaker_arg(raw):
    payload = esc(raw)
    m = SPEAKER_RE.match(payload)
    if m and m.group('name').strip() != '':
        return clean_name(unesc(m.group('name'))), unesc(m.group('speaker').strip())
    text = unesc(payload.strip())
    if text.startswith('[') and text.endswith(']'):
        return '', text[1:-1]
    # malformed name such as 'MSG_BTLSTART_00 [礼司]]': recover the speaker
    open_at = text.rfind('[')
    if open_at > 0:
        tail = text[open_at + 1:].rstrip(']').strip()
        if tail:
            return clean_name(text[:open_at]), tail
    return clean_name(text), None


def split_tokens(line):
    pieces, buf, i, n = [], [], 0, len(line)
    while i < n:
        ch = line[i]
        if ch == '[':
            if buf:
                pieces.append(('text', ''.join(buf)))
                buf = []
            end = line.find(']', i)
            if end == -1:
                buf.append(ch)
                i += 1
                continue
            pieces.append(('tag', line[i + 1:end]))
            i = end + 1
        else:
            buf.append(ch)
            i += 1
    if buf:
        pieces.append(('text', ''.join(buf)))
    return pieces


def readable_text(pieces):
    out = []
    for kind, value in pieces:
        if kind == 'text':
            out.append(unesc(value))
        else:
            tag = value.split(' ', 1)[0].lower()
            if tag in NEWLINE_TAGS:
                out.append('\n')
            elif tag not in DROP_TAGS:
                out.append('[' + unesc(value) + ']')
    text = ''.join(out).replace('\r\n', '\n')
    lines = [ln.strip() for ln in text.split('\n')]
    return '\n'.join(ln for ln in lines if ln != '').strip()


def voice_of(pieces):
    for kind, value in pieces:
        if kind == 'tag' and value.split(' ', 1)[0].lower() == 'vp':
            return value
    return None


def parse_msg_file(path):
    with open(path, encoding='utf-8') as fh:
        raw_lines = fh.read().split('\n')

    dialogs, current = [], None
    for raw in raw_lines:
        line = raw.rstrip('\r')
        m = MSG_HEADER.match(line)
        if m:
            name, speaker = strip_speaker_arg(m.group(1))
            current = {'kind': 'msg', 'name': name, 'speaker': speaker, 'lines': []}
            dialogs.append(current)
            continue
        m = SEL_HEADER.match(line)
        if m:
            payload = esc(m.group(1))
            parts = payload.rsplit(' ', 1)
            name = unesc(parts[0].strip())
            pattern = parts[1].strip() if len(parts) == 2 else ''
            current = {'kind': 'sel', 'name': name, 'speaker': None,
                       'pattern': pattern, 'lines': []}
            dialogs.append(current)
            continue
        if line.startswith('[s]') and current is not None:
            body = line[3:]
            if body.endswith('[e]'):
                body = body[:-3]
            current['lines'].append(body)
            continue

    for d in dialogs:
        texts, voices = [], []
        for body in d['lines']:
            pieces = split_tokens(body)
            t = readable_text(pieces)
            v = voice_of(pieces)
            if v:
                voices.append(v)
            if t:
                texts.append(t)
        d['text'] = '\n'.join(texts).strip()
        d['voice'] = voices[0] if voices else None
    return dialogs


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------

# Whole subtrees that hold engine / UI / gameplay text rather than speech.
# Each entry is a lower-case literal path fragment (prefix match on the relative path).
EXCLUDED_PREFIXES = [
    'battle\\gui\\', 'battle\\result\\', 'battle\\analyze\\', 'battle\\table\\',
    'battle\\cutin\\', 'battle\\tutorial\\', 'battle\\message\\',
    'device\\', 'network\\', 'init\\', 'title\\', 'game\\',
    'field\\box\\', 'field\\hit\\', 'field\\object_hit\\',
    'field\\panel\\', 'field\\ftd\\', 'field\\init\\', 'field\\enemy\\',
    'field\\telop\\',
    'community\\event\\message\\',
    'tutorial\\',
]

# Text that is plainly a system/UI notification rather than speech or narration.
SYSTEM_NOTICE = re.compile(
    r'^(?:可以|已经可以|现在可以|已|无法|不能|没有|未持有|使用不能|系统)'
    r'|(?:失败|错误|无法|不能)(?:了)?[。！]?$'
)

PLACEHOLDER = re.compile(r'^[…\.・\-ー\s　]*$|^[×xX]+$', re.I)

# Debug leftovers: dummy / test / 「(暂定)」 placeholder entries that shipped in
# the data and are not real script text.
DEBUG_NAME = re.compile(r'(?:^|_)(?:dummy|test)(?:_|$)', re.I)
DEBUG_TEXT = re.compile(r'^\s*[（(](?:暂定|仮|dummy|test)[）)]|^\s*(?:Ｄｕｍｍｙ|dummy|Dummy)\s*$')

# In-game data errors: speaker labels that are typo'd in the shipped Chinese
# script. Verified against the original binaries (the bytes really do encode the
# wrong character, so this is not a decoding problem) and against every other
# line that speaker says.
#   礼司 -> 龙司 : 坂本龙司 (Ryuji). 123 occurrences; 礼 and 龙 are unrelated
#                 code points (charset indices 2365 vs 2468), all other
#                 character names decode correctly.
SPEAKER_FIXES = {
    '礼司': '坂本　龙司',
}

# number of times each fix actually had to be applied (filled in by main())
SPEAKER_FIXES_APPLIED = collections.Counter()


def apply_speaker_fixes(dialogs):
    """Map known bad speaker labels to the intended name.

    Records the original label in 'speaker_raw' so a consumer can show that the
    entry was corrected. Returns the number of dialogs changed.
    """
    changed = 0
    for d in dialogs:
        raw = d.get('speaker')
        if raw in SPEAKER_FIXES:
            d['speaker_raw'] = raw
            d['speaker'] = SPEAKER_FIXES[raw]
            changed += 1
    return changed


def is_excluded(rel):
    low = rel.lower()
    for prefix in EXCLUDED_PREFIXES:
        if prefix in low:
            return True
    return False


def category_of(rel):
    parts = rel.split('\\')
    top = parts[0].upper()
    if top == 'EVENT_DATA':
        # keep the event chapter folder (E100..E900) as a sub-category
        if len(parts) > 3:
            return 'EVENT_DATA\\' + parts[2]
        return 'EVENT_DATA'
    if top == 'FIELD' and len(parts) > 1:
        return 'FIELD\\' + parts[1]
    if top == 'SCRIPT':
        return 'SCRIPT_FIELD'
    return top


def keep_dialog(d):
    text = d['text']
    if not text or PLACEHOLDER.match(text):
        return False
    if DEBUG_NAME.search(d['name']) or DEBUG_TEXT.match(text):
        return False
    if d['kind'] == 'sel':
        return True
    # a labelled speaker is always real speech
    if d['speaker'] is not None:
        return True
    # unlabelled: keep narration, drop obvious system notices
    if SYSTEM_NOTICE.match(text):
        return False
    return True


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def safe_name(rel):
    return rel.replace('\\', '__')


def main():
    if not os.path.isdir(STAGING):
        sys.exit('staging dir missing: ' + STAGING)

    files = []
    for dirpath, _dirs, names in os.walk(STAGING):
        for fn in names:
            if fn.lower().endswith('.msg'):
                files.append(os.path.join(dirpath, fn))
    files.sort(key=lambda p: os.path.relpath(p, STAGING).lower())
    print('decompiled .msg files:', len(files))

    if os.path.isdir(OUTPUT):
        for root, dirs, names in os.walk(OUTPUT, topdown=False):
            for n in names:
                os.remove(os.path.join(root, n))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
    os.makedirs(OUTPUT, exist_ok=True)

    per_cat = collections.Counter()
    per_cat_files = collections.Counter()
    skipped_files = 0
    total_kept = 0
    fixed_count = 0
    catalogue = []

    for path in files:
        rel = os.path.relpath(path, STAGING)
        rel_src = rel[:-4] if rel.lower().endswith('.msg') else rel
        if is_excluded(rel_src):
            skipped_files += 1
            continue
        dialogs = parse_msg_file(path)
        apply_speaker_fixes(dialogs)
        kept = [d for d in dialogs if keep_dialog(d)]
        for d in kept:
            if d.get('speaker_raw'):
                SPEAKER_FIXES_APPLIED[d['speaker_raw']] += 1
        if not kept:
            skipped_files += 1
            continue

        cat = category_of(rel_src)
        cat_dir = os.path.join(OUTPUT, cat)
        os.makedirs(cat_dir, exist_ok=True)
        out_path = os.path.join(cat_dir, safe_name(rel_src) + '.txt')

        lines = []
        lines.append('=' * 80)
        lines.append('来源文件: ' + rel_src)
        lines.append('对话条目: {} 条'.format(len(kept)))
        lines.append('=' * 80)
        lines.append('')
        for d in kept:
            fixed = d.get('speaker_raw')
            if d['kind'] == 'sel':
                lines.append('【选项】' + d['name'])
                for opt in d['text'].split('\n'):
                    lines.append('    ▸ ' + opt)
            else:
                speaker = d['speaker']
                if speaker is None:
                    head = '〔旁白〕'
                elif speaker.isdigit():
                    head = '〔主人公〕' if speaker == '0' else '〔说话人{0}〕'.format(speaker)
                else:
                    head = '【{0}】'.format(speaker)
                body = d['text'].replace('\n', '\n    ')
                lines.append('{0}{1}'.format(head, body))
            lines.append('    «ID {0}  {1}»'.format(d['name'], '选项' if d['kind'] == 'sel' else '对话'))
            if fixed:
                lines.append('    （原始数据中说话人误写作「{0}」，已修正）'.format(fixed))
            lines.append('')

        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))

        per_cat[cat] += len(kept)
        per_cat_files[cat] += 1
        total_kept += len(kept)
        fixed_count += sum(1 for d in kept if d.get('speaker_raw'))
        catalogue.append((cat, rel_src, out_path, len(kept)))

    # ---- index ----
    idx = []
    idx.append('# P5R 对话脚本总目录')
    idx.append('')
    idx.append('本目录由 Atlus Script Tools 反编译 + 结构化整理生成，仅包含剧情与对话文本。')
    idx.append('')
    idx.append('| 分类 | 文件数 | 对话条数 |')
    idx.append('| --- | ---: | ---: |')
    for cat in sorted(per_cat, key=lambda c: -per_cat[c]):
        idx.append('| {0} | {1} | {2} |'.format(cat, per_cat_files[cat], per_cat[cat]))
    idx.append('| **合计** | **{0}** | **{1}** |'.format(sum(per_cat_files.values()), total_kept))
    idx.append('')
    idx.append('跳过的文件（战斗/教程/系统UI等非对话内容）: {0}'.format(skipped_files))
    idx.append('')
    if fixed_count:
        idx.append('已修正的说话人名（游戏数据本身的错字，非解码问题）:')
        idx.append('')
        for wrong in sorted(SPEAKER_FIXES_APPLIED):
            idx.append('- 「{0}」→「{1}」  （{2} 条）'.format(
                wrong, SPEAKER_FIXES[wrong], SPEAKER_FIXES_APPLIED[wrong]))
        idx.append('')
        idx.append('共修正 {0} 条，修正处已在正文中以「原始数据中说话人误写作…」标注。'.format(fixed_count))
        idx.append('')
    for cat in sorted(per_cat):
        idx.append('## ' + cat)
        idx.append('')
        for c, rel, out, n in catalogue:
            if c != cat:
                continue
            idx.append('- [{0}]({1}) — {2} 条'.format(
                rel, os.path.relpath(out, OUTPUT).replace('\\', '/'), n))
        idx.append('')

    with open(os.path.join(OUTPUT, INDEX_NAME), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(idx))

    print('categories        :', len(per_cat))
    print('files written     :', sum(per_cat_files.values()))
    print('files skipped     :', skipped_files)
    print('dialogs written   :', total_kept)
    print('speaker fixes     :', fixed_count)
    print()
    for cat in sorted(per_cat, key=lambda c: -per_cat[c]):
        print('  {:24} files={:<5} dialogs={}'.format(cat, per_cat_files[cat], per_cat[cat]))


if __name__ == '__main__':
    main()
