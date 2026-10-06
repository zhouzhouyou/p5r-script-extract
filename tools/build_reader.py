#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the data set for the P5R script reader.

Reads the decompiled .msg tree, groups every dialog into a *scene*, classifies
each scene on three levels (category -> chapter -> scene) and writes:

  reader/data/index.json      scene index + filter vocabulary (small, loaded first)
  reader/data/scenes/*.json   dialog content, one file per category (lazy loaded)

Run from the workspace root:  python _tools/build_reader.py
"""

import os
import re
import json
import collections
import importlib.util

# Paths are derived from this file's location so the tools work from any checkout:
#   <root>/tools/build_reader.py  ->  <root>/_staging/decompiled, <root>/reader
# Override with the P5R_ROOT environment variable if needed.
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('P5R_ROOT') or os.path.dirname(_HERE)

STAGING = os.path.join(ROOT, '_staging', 'decompiled')
READER = os.path.join(ROOT, 'reader')

# ------------------------------------------------- shared data corrections
# build_script.py owns the in-game data corrections (bad speaker labels etc.)
# so the plain-text script and the reader can never disagree about them.
_bs_spec = importlib.util.spec_from_file_location(
    'build_script', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_script.py'))
build_script = importlib.util.module_from_spec(_bs_spec)
_bs_spec.loader.exec_module(build_script)
SPEAKER_FIXES = build_script.SPEAKER_FIXES

# ---------------------------------------------------------------- .msg parser

MSG_HEADER = re.compile(r'^\[msg\s+(.*)$')
SEL_HEADER = re.compile(r'^\[sel\s+(.*)$')
SPEAKER_RE = re.compile(r'^(?P<name>.*?)\s*\[(?P<speaker>[^\[\]]*)\]$', re.S)

DROP_TAGS = {'clr', 'bup', 'f', 'vp', 'w', 'e', 'n', 'b', 'v', 'x', 's',
             'sel', 'msg', 'ref', 'dlg', 'we', 'nwe', 'cut'}
NEWLINE_TAGS = {'n', 'nwe'}
ESC_OPEN, ESC_CLOSE = '\x00O\x00', '\x00C\x00'


def esc(t):
    return t.replace('\\[', ESC_OPEN).replace('\\]', ESC_CLOSE)


def unesc(t):
    return t.replace(ESC_OPEN, '[').replace(ESC_CLOSE, ']')


def clean_name(n):
    n = n.strip()
    while n.endswith(']'):
        n = n[:-1].rstrip()
    return n.strip().strip('`').strip()


def split_header(raw):
    payload = esc(raw)
    m = SPEAKER_RE.match(payload)
    if m and m.group('name').strip():
        return clean_name(unesc(m.group('name'))), unesc(m.group('speaker').strip())
    text = unesc(payload.strip())
    if text.startswith('[') and text.endswith(']'):
        return '', text[1:-1]
    i = text.rfind('[')
    if i > 0:
        tail = text[i + 1:].rstrip(']').strip()
        if tail:
            return clean_name(text[:i]), tail
    return clean_name(text), None


def split_tokens(line):
    pieces, buf, i, n = [], [], 0, len(line)
    while i < n:
        if line[i] == '[':
            if buf:
                pieces.append(('t', ''.join(buf)))
                buf = []
            end = line.find(']', i)
            if end == -1:
                buf.append(line[i])
                i += 1
                continue
            pieces.append(('g', line[i + 1:end]))
            i = end + 1
        else:
            buf.append(line[i])
            i += 1
    if buf:
        pieces.append(('t', ''.join(buf)))
    return pieces


def render(pieces):
    out = []
    for kind, value in pieces:
        if kind == 't':
            out.append(unesc(value))
        else:
            tag = value.split(' ', 1)[0].lower()
            if tag in NEWLINE_TAGS:
                out.append('\n')
            elif tag not in DROP_TAGS:
                out.append('[' + unesc(value) + ']')
    text = ''.join(out).replace('\r\n', '\n')
    return '\n'.join(x.strip() for x in text.split('\n') if x.strip()).strip()


def parse(path):
    dialogs, cur = [], None
    for raw in open(path, encoding='utf-8').read().split('\n'):
        line = raw.rstrip('\r')
        m = MSG_HEADER.match(line)
        if m:
            name, speaker = split_header(m.group(1))
            cur = {'kind': 'msg', 'name': name, 'speaker': speaker, 'lines': []}
            dialogs.append(cur)
            continue
        m = SEL_HEADER.match(line)
        if m:
            payload = esc(m.group(1))
            parts = payload.rsplit(' ', 1)
            cur = {'kind': 'sel', 'name': unesc(parts[0].strip()), 'speaker': None,
                   'pattern': parts[1].strip() if len(parts) == 2 else '', 'lines': []}
            dialogs.append(cur)
            continue
        if line.startswith('[s]') and cur is not None:
            body = line[3:]
            if body.endswith('[e]'):
                body = body[:-3]
            cur['lines'].append(body)
    for d in dialogs:
        texts = []
        for body in d['lines']:
            t = render(split_tokens(body))
            if t:
                texts.append(t)
        d['text'] = '\n'.join(texts).strip()
    return dialogs


# ------------------------------------------------------------- classification

OUT_OF_SCOPE = ('battle\\gui\\', 'battle\\result\\', 'battle\\analyze\\', 'battle\\table\\',
                'battle\\cutin\\', 'battle\\tutorial\\', 'battle\\message\\',
                'device\\', 'network\\', 'init\\', 'title\\', 'game\\',
                'field\\box\\', 'field\\hit\\', 'field\\object_hit\\', 'field\\panel\\',
                'field\\ftd\\', 'field\\init\\', 'field\\enemy\\', 'field\\telop\\',
                'community\\event\\message\\', 'tutorial\\')

PLACEHOLDER = re.compile(r'^[…\.・\-ー\s　]*$|^[×xX]+$')
DEBUG_NAME = re.compile(r'(?:^|_)(?:dummy|test)(?:_|$)', re.I)
DEBUG_TEXT = re.compile(r'^\s*[（(](?:暂定|仮|dummy|test)[）)]|^\s*(?:Ｄｕｍｍｙ|dummy)\s*$', re.I)
SYSTEM_NOTICE = re.compile(r'^(?:可以|已经可以|现在可以|已|无法|不能|没有|未持有|使用不能|系统)'
                           r'|(?:失败|错误)(?:了)?[。！]?$')

DAY_RE = re.compile(r'(?<![A-Za-z0-9])D(\d{2})(?!\d)')
TIME_WORD = re.compile(r'(?:^|_)(MORNING|NOON|EVENING|NIGHT|DAYTIME|AFTERNOON)(?:_|$)')
# engine variable placeholders inside dialogue text, e.g. [fName] [lName] [group]
VAR_TAG = re.compile(r'\[([A-Za-z_][A-Za-z0-9_]*)\]')

# confidant code -> (display name, group); derived from FIELD\NPC\CORPxxx
CONFIDANT = {
    'C000': ('卡萝莉娜', '天鹅绒房间'),
    'C001': ('摩尔加纳', '怪盗团'),
    'C002': ('新岛真', '怪盗团'),
    'C003': ('奥村春', '怪盗团'),
    'C004': ('喜多川佑介', '怪盗团'),
    'C005': ('佐仓惣治郎', '协助人'),
    'C006': ('高卷杏', '怪盗团'),
    'C007': ('坂本龙司', '怪盗团'),
    'C008': ('明智吾郎', '协助人'),
    'C009': ('佐仓双叶', '怪盗团'),
    'C010': ('御船千早', '协助人'),
    'C011': ('芮丝汀娜 / 卡萝莉娜', '天鹅绒房间'),
    'C012': ('岩井宗久', '协助人'),
    'C013': ('武见妙', '协助人'),
    'C014': ('川上贞代', '协助人'),
    'C015': ('大宅一子', '协助人'),
    'C016': ('织田信也', '协助人'),
    'C017': ('东乡一二三', '协助人'),
    'C018': ('三岛由辉', '协助人'),
    'C019': ('吉田寅之助', '协助人'),
    'C020': ('新岛冴', '剧情人物'),
    'C021': ('（测试）', None),
    'C022': ('芳泽堇 / 霞', '怪盗团'),
    'C023': ('丸喜拓人', '协助人'),
    'C099': ('（测试）', None),
}

CATEGORY_META = {
    'main':      '主线剧情',
    'confidant': '协助人剧情',
    'script':    '剧情脚本',
    'daily':     '日常与城镇',
    'battle':    '战斗对白',
    'facility':  '设施与天鹅绒房间',
    'mypalace':  '我的宫殿',
}

# browse order for the reader sidebar: story progression first
CATEGORY_ORDER = ['main', 'script', 'confidant', 'daily', 'battle', 'facility', 'mypalace']

# palace-number -> human label, for EVENT_DATA main-story chapters
PALACE_LABEL = {
    'E0': '序章', 'E1': '第一部', 'E2': '第二部', 'E3': '第三部',
    'E4': '第四部', 'E5': '第五部', 'E6': '第六部', 'E7': '第七部',
    'E8': '第八部', 'E9': '尾声与追加',
}

# chapter sort keys so the reader can present things in story order
CHAPTER_ORDER = {
    'main': {k: i for i, k in enumerate(PALACE_LABEL)},
    'confidant': {},
}


# A page should be a comfortable read: long enough to be one meaningful beat,
# short enough that scrolling back is not painful. Heavier than this and the
# reader gets pages tens of thousands of pixels tall (measured 93k at 900 lines).
MAX_SCENE_LINES = 400
MAX_SCENE_CHARS = 5000


def classify(rel):
    """rel: source path relative to P5RScript, e.g. 'EVENT_DATA\\MESSAGE\\E700\\E700_300.BMD'
    Returns (category, chapter_key, chapter_label, scene_key, scene_label, prefer) or None."""
    prefer = 'merge'
    p = rel.replace('/', '\\')
    top = p.split('\\')[0].upper()
    parts = p.split('\\')
    base = parts[-1]

    if top == 'EVENT_DATA':
        m = re.match(r'E(\d)(\d{2})', base)
        if not m:
            return None
        pal = m.group(1)
        ev = 'E' + m.group(1) + m.group(2)
        ch = 'E' + pal
        return ('main', ch, PALACE_LABEL.get(ch, ch), ev, ev, 'own')

    if top == 'SCRIPT':
        m = re.match(r'(FSCR\d{4})_(\d{3})_(\d{3})', base)
        if not m:
            return None
        area, minor, idx = m.group(1).upper(), m.group(2), m.group(3)
        return ('script', area, '剧情脚本 ' + area, area + '_' + minor + '_' + idx,
                f'{area}_{minor}_{idx}', 'own')

    if top == 'FIELD':
        sub = parts[1].upper() if len(parts) > 1 else ''
        if sub == 'NPC':
            m = re.match(r'CORP(\d+)', base)
            if m:
                code = 'C' + m.group(1)
                name, group = CONFIDANT.get(code, (code, '其他'))
                if group is None:          # test / debug entries
                    return None
                return ('confidant', code, name, code, name, 'own')
            # FNPC / FEV … : ordinary town NPCs, not confidants
            return ('daily', 'NPC', '城镇 NPC', 'NPC_' + base, 'NPC ' + base, 'own')
        if sub == 'KF_EVENT':
            kind = (parts[2].upper() if len(parts) > 2 else '') or 'EVENT'
            m = re.match(r'([A-Za-z]+?)(\d{3})', base)
            grp = (m.group(1) + m.group(2)).upper() if m else base
            label = '城镇事件' if kind == 'NPC' else f'城镇事件 {kind}'
            return ('daily', 'KF_' + kind, label, 'KF_' + grp, '事件 ' + grp, 'own')
        if sub == 'MY_PALACE':
            kind = parts[2].upper() if len(parts) > 2 else ''
            m = re.match(r'([A-Za-z]+?)(\d{3})', base)
            grp = (m.group(1) + m.group(2)).upper() if m else base
            return ('daily', 'MYP_' + kind, '我的宫殿 ' + kind, 'MYP' + grp,
                    '宫殿 ' + grp, 'own')
        mapping = {'SAFETY_ROOM': ('SAFE', '安全屋与提示'), 'PARTY': ('PARTY', '同伴对话'),
                   'TV': ('TV', '电视节目'), 'DOOR': ('DOOR', '门与场景描写'),
                   'ETC': ('ETC', '其他场景'), 'SCRIPT': ('BOSS', 'BOSS 脚本')}
        if sub in mapping:
            k, label = mapping[sub]
            return ('daily', k, label, k, label, 'merge')
        return ('daily', sub or 'FIELD', '场景 ' + (sub or 'FIELD'),
                sub or 'FIELD', sub or 'FIELD', 'merge')

    if top == 'CAMP':
        # every file is one short chat; merge them so a chapter reads continuously
        return ('daily', 'CHAT', '同伴闲聊', 'CHAT', '同伴闲聊', 'merge')

    if top == 'BATTLE':
        sub = parts[1].upper() if len(parts) > 1 else ''
        if sub == 'TALK':
            m = re.match(r'([A-Za-z]+?)(\d*)', base)
            grp = (m.group(1) or base).upper()
            return ('battle', 'TALK', '战斗对白', 'TALK_' + grp, '战斗对白 ' + grp, 'own')
        return ('battle', 'EVENT', '战斗事件', 'EVENT_' + base, base, 'own')

    if top == 'FACILITY':
        return ('facility', 'FCL', '设施与天鹅绒房间', 'FCL_' + base, base, 'own')

    if top == 'MYPALACE':
        sub = parts[1].upper() if len(parts) > 1 else 'MYP'
        return ('mypalace', sub, '我的宫殿 ' + sub, sub, sub, 'own')

    if top == 'MINIGAME':
        return ('daily', 'MINIGAME', '小游戏', 'MINIGAME_' + base, base, 'own')

    return None


def keep(d):
    text = d['text']
    if not text or PLACEHOLDER.match(text):
        return False
    if DEBUG_NAME.search(d['name']) or DEBUG_TEXT.match(text):
        return False
    if d['kind'] == 'sel':
        return True
    if d['speaker'] is not None:
        return True
    return not SYSTEM_NOTICE.match(text)


def main():
    files = []
    for dp, _dn, fn in os.walk(STAGING):
        for f in fn:
            if f.lower().endswith('.msg') and not f.lower().endswith('.msg.h'):
                files.append(os.path.join(dp, f))
    files.sort(key=lambda p: os.path.relpath(p, STAGING).lower())

    scenes = {}
    skipped = 0
    in_scope = 0
    total_lines = 0
    fix_count = 0
    fixed_labels = {}
    speaker_counter = collections.Counter()
    var_counter = collections.Counter()

    for path in files:
        rel = os.path.relpath(path, STAGING)
        rel_src = rel[:-4]
        if any(x in rel_src.lower() for x in OUT_OF_SCOPE):
            skipped += 1
            continue
        cls = classify(rel_src)
        if cls is None:
            skipped += 1
            continue
        cat, ch_key, ch_label, sc_key, sc_label, prefer = cls

        parsed = parse(path)
        fix_count += build_script.apply_speaker_fixes(parsed)
        for d in parsed:
            if d.get('speaker_raw'):
                fixed_labels[d['speaker_raw']] = d['speaker']
        # Keep EVERY message, including empty / placeholder / debug ones.
        # Dropping any would shift every later dialog down by one and break the
        # index correspondence with .msg.h that the flow-derived timeline relies
        # on (measured: 2136 dropped messages across 1279 files). Rendering of
        # empty entries is handled in the UI instead.
        dialogs = parsed
        if not dialogs:
            skipped += 1
            continue
        in_scope += 1
        sid = '{}|{}|{}'.format(cat, ch_key, sc_key)
        scene = scenes.get(sid)
        if scene is None:
            scene = scenes[sid] = {
                'id': sid, 'category': cat, 'chapter': ch_key, 'chapterLabel': ch_label,
                'key': sc_key, 'label': sc_label, 'prefer': prefer,
                'files': [], 'dialogs': [], 'days': [], 'times': [],
            }
        scene['files'].append(rel_src)

        for d in dialogs:
            speaker = d['speaker']
            if speaker is None:
                who, kind = '旁白', 'narration'
            elif speaker.isdigit():
                who = '主人公' if speaker == '0' else '说话人' + speaker
                kind = 'speech'
            else:
                who, kind = speaker, 'speech'
            if kind == 'speech':
                speaker_counter[who] += 1
            days = DAY_RE.findall(d['name'])
            times = TIME_WORD.findall(d['name'])
            for v in VAR_TAG.findall(d['text']):
                var_counter[v] += 1
            scene['dialogs'].append({
                'i': d['name'],
                'k': d['kind'],
                's': who,
                't': d['text'],
                'd': days[0] if days else None,
                'm': times[0] if times else None,
                'f': rel_src,
            })
            for x in days:
                if x not in scene['days']:
                    scene['days'].append(x)
            for x in times:
                if x not in scene['times']:
                    scene['times'].append(x)
            total_lines += 1

    # ---- merge "prefer=merge" scenes into chapter-level blocks, then split
    #      everything that is still too long so one page stays readable ----
    merged = {}
    passthrough = []
    for sc in scenes.values():
        if sc['prefer'] == 'merge':
            key = (sc['category'], sc['chapter'])
            tgt = merged.get(key)
            if tgt is None:
                tgt = merged[key] = {
                    'id': '{}|{}|*'.format(*key), 'category': sc['category'],
                    'chapter': sc['chapter'], 'chapterLabel': sc['chapterLabel'],
                    'key': '*', 'label': sc['chapterLabel'], 'prefer': 'merge',
                    'files': [], 'dialogs': [], 'days': [], 'times': [],
                }
            tgt['files'].extend(sc['files'])
            tgt['dialogs'].extend(sc['dialogs'])
            for x in sc['days']:
                if x not in tgt['days']:
                    tgt['days'].append(x)
            for x in sc['times']:
                if x not in tgt['times']:
                    tgt['times'].append(x)
        else:
            passthrough.append(sc)

    blocks = passthrough + list(merged.values())

    def chunk_dialogs(dialogs):
        """Split on whichever limit is hit first, so a page stays a comfortable read."""
        parts, cur, chars = [], [], 0
        for d in dialogs:
            n = len(d['t'])
            if cur and (len(cur) >= MAX_SCENE_LINES or chars + n > MAX_SCENE_CHARS):
                parts.append(cur)
                cur, chars = [], 0
            cur.append(d)
            chars += n
        if cur:
            parts.append(cur)
        return parts

    final = []
    for sc in blocks:
        if len(sc['dialogs']) <= MAX_SCENE_LINES and \
           sum(len(d['t']) for d in sc['dialogs']) <= MAX_SCENE_CHARS:
            sc['files'] = sorted(set(sc['files']))
            final.append(sc)
            continue
        parts = chunk_dialogs(sc['dialogs'])
        for n, chunk in enumerate(parts, 1):
            files = sorted({d['f'] for d in chunk})
            final.append({
                'id': '{}#{}'.format(sc['id'], n), 'category': sc['category'],
                'chapter': sc['chapter'], 'chapterLabel': sc['chapterLabel'],
                'key': sc['key'], 'label': '{}（{}/{}）'.format(sc['label'], n, len(parts)),
                'prefer': sc['prefer'], 'files': files, 'dialogs': chunk,
                'days': sorted({d['d'] for d in chunk if d['d']}),
                'times': sorted({d['m'] for d in chunk if d['m']}),
            })

    scenes = {s['id']: s for s in final}

    # ---- normalise scene list ----
    # For 'daily' the chapter is a thematic bucket (CHAT / SAFE / …), so order by
    # scene key instead to keep numeric continuity (闲聊 001, 002, …).
    def scene_sort_key(s):
        if s['category'] == 'daily':
            return (3, s['chapter'], s['key'])
        return (CATEGORY_ORDER.index(s['category'])
                if s['category'] in CATEGORY_ORDER else 9,
                s['chapter'], s['key'])

    ordered = sorted(scenes.values(), key=scene_sort_key)

    # ---- how many dialogs each source file contributes, per scene ----
    # Needed to shift a merged scene's timeline indices into the concatenated
    # dlg array (see the timeline section below).
    file_dlg_count = collections.Counter()
    for s in ordered:
        for d in s['dialogs']:
            file_dlg_count[d['f']] += 1

    def _shift(node, off):
        """Offset every dialog index in a timeline item by `off`."""
        if not off:
            return node
        if isinstance(node, list):
            return [_shift(x, off) for x in node]
        if isinstance(node, int):
            return node + off
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k == 'branches':
                    out[k] = [[_shift(x, off) for x in br] for br in v]
                elif k in ('sel', 'varMsg') and isinstance(v, int):
                    out[k] = v + off
                else:
                    out[k] = v
            return out
        return node

    index_scenes = []
    cat_counter = collections.Counter()
    ch_seen = {}
    for s in ordered:
        cat_counter[s['category']] += 1
        s['days'].sort()
        s['times'].sort()
        s['count'] = len(s['dialogs'])
        # first line preview used by the scene list
        first = s['dialogs'][0]
        s['preview'] = (first['t'].replace('\n', ' '))[:60]
        s['speakers'] = sorted({d['s'] for d in s['dialogs'] if d['s'] != '旁白'})
        index_scenes.append({
            'id': s['id'], 'c': s['category'], 'ch': s['chapter'], 'chl': s['chapterLabel'],
            'k': s['key'], 'l': s['label'], 'n': s['count'],
            'p': s['preview'], 'd': s['days'], 'm': s['times'],
            'sp': s['speakers'][:8], 'src': s['files'][0],
        })
        ch_seen.setdefault(s['category'], {})[s['chapter']] = s['chapterLabel']

    os.makedirs(os.path.join(READER, 'data', 'scenes'), exist_ok=True)

    # ---- per-category content files ----
    for cat in cat_counter:
        payload = {}
        for s in ordered:
            if s['category'] != cat:
                continue
            payload[s['id']] = {
                'l': s['label'], 'chl': s['chapterLabel'], 'src': s['files'],
                'dlg': [{'s': d['s'], 't': d['t'], 'k': d['k'], 'i': d['i'],
                         'd': d['d'], 'm': d['m'], 'f': d['f']} for d in s['dialogs']],
            }
        outp = os.path.join(READER, 'data', 'scenes', cat + '.json')
        with open(outp, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(',', ':'))

    # ---- per-category timeline files (choice branches, lazy loaded) ----
    # Produced by build_timeline.py from the decompiled .flow scripts. A scene
    # can span several source files, so its timeline is the concatenation of
    # each contributing file's sequence.
    tl_path = os.path.join(STAGING, '..', 'timeline.json')
    tl_path = os.path.abspath(tl_path)
    timeline_ok = 0
    tl_dir = os.path.join(READER, 'data', 'timeline')
    if os.path.exists(tl_path):
        with open(tl_path, encoding='utf-8') as fh:
            timelines = json.load(fh)
        os.makedirs(tl_dir, exist_ok=True)
        for cat in cat_counter:
            tl_payload = {}
            for s in ordered:
                if s['category'] != cat:
                    continue
                # A scene can merge several source files, and the reader's dlg
                # array is their concatenation in file order. Shift each file's
                # message indices by how many dialogs precede it, otherwise the
                # timeline points at the wrong dialog.
                merged, dyn = [], []
                offset = 0
                for f in s['files']:
                    t = timelines.get(f)
                    if not t:
                        continue
                    merged.extend(_shift(list(t.get('seq', [])), offset))
                    dyn.extend(t.get('dyn', []))
                    offset += file_dlg_count.get(f, 0)
                if merged or dyn:
                    tl_payload[s['id']] = {'seq': merged, 'dyn': dyn}
                    timeline_ok += 1
            with open(os.path.join(tl_dir, cat + '.json'), 'w', encoding='utf-8') as fh:
                json.dump(tl_payload, fh, ensure_ascii=False, separators=(',', ':'))
        index_timeline = {'scenes': timeline_ok,
                          'source': 'build_timeline.py (from _staging/flow)'}
    else:
        index_timeline = None
        print('!! timeline.json not found - run _tools/build_timeline.py first')

    index = {
        'generatedFrom': 'C:\\Users\\14453\\Documents\\P5RScript',
        'categories': [{'id': c, 'label': CATEGORY_META.get(c, c), 'scenes': cat_counter[c],
                        'chapters': [{'id': k, 'label': v}
                                     for k, v in sorted(ch_seen[c].items())]}
                       for c in sorted(cat_counter,
                                       key=lambda x: (CATEGORY_ORDER.index(x)
                                                      if x in CATEGORY_ORDER else 9))],
        'speakers': [{'n': n, 'c': c} for n, c in speaker_counter.most_common()],
        'vars': [{'n': n, 'c': c} for n, c in var_counter.most_common()],
        # in-game data errors that were corrected while building this data set
        'dataFixes': {
            'count': fix_count,
            'speakers': [{'from': k, 'to': v, 'count': speaker_counter.get(v, 0)}
                         for k, v in sorted(fixed_labels.items())],
        },
        'totals': {'scenes': len(index_scenes), 'lines': total_lines,
                   'files': in_scope, 'skipped': skipped},
        'timeline': index_timeline,
        'scenes': index_scenes,
    }
    with open(os.path.join(READER, 'data', 'index.json'), 'w', encoding='utf-8') as fh:
        json.dump(index, fh, ensure_ascii=False, separators=(',', ':'))

    print('scenes :', len(index_scenes))
    print('lines  :', total_lines)
    print('skipped:', skipped)
    if fix_count:
        print('data fixes:', fix_count, '->',
              ', '.join('{}→{}'.format(k, v) for k, v in sorted(fixed_labels.items())))
    for c in sorted(cat_counter, key=lambda x: -cat_counter[x]):
        print('  {:11} scenes={}'.format(c, cat_counter[c]))
    print('speakers:', len(speaker_counter))
    for n, c in speaker_counter.most_common(12):
        print('   {:20} {}'.format(n, c))


if __name__ == '__main__':
    main()
