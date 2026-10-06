#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build a per-scene "timeline" from the decompiled flow scripts, so the reader can
show which dialogue follows which choice.

Verified fact (see _tools/check_msgid_mapping.py, whole corpus): a flow call
argument IS the message index in the matching .msg.h --
    MSG(3, 0) -> message 3      SEL(2) -> selection 2
The one known exception is EVENT_DATA\\SCRIPT\\E700\\E700_300.BF, whose
MESSAGE_REF args address an external message pool; those are reported as
external references rather than mapped to a wrong dialog.

Output: _staging/timeline.json
  { "<source path>": {
        "seq":  [ <order item>, ... ],      # top-level, always-executed order
        "dyn":  [ "<condition>", ... ]      # conditions we cannot resolve
    } }
  where an <order item> is either
        <int>                                dialog index
        {"sel": <int>}                       selection dialog index
        {"cond": "<c>", "var": "v", "values": [..],
         "branches": [[ <order item>, ... ], ...]}

This is the canonical per-source build. build_reader.py converts it into
per-category files under reader/data/timeline/ for the reader to lazy-load.
"""

import os
import re
import sys
import json

# Paths are derived from this file's location so the tools work from any checkout:
#   <root>/tools/build_timeline.py  ->  <root>/_staging, <root>/reader
# Override with the P5R_ROOT environment variable if needed.
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('P5R_ROOT') or os.path.dirname(_HERE)

STAGING = os.path.join(ROOT, '_staging')
DEC = os.path.join(STAGING, 'decompiled')
FLOW = os.path.join(STAGING, 'flow')
OUT = os.path.join(STAGING, 'timeline.json')

HDR = re.compile(r'^const int (.+?)\s+=\s+(\d+);')
IF_LINE = re.compile(r'^if\s*\((.*)\)\s*$')
ELSEIF_LINE = re.compile(r'^else\s+if\s*\((.*)\)\s*$')
VAR_EQ = re.compile(r'^(\w+)\s*=\s*(.+)$')
CALL = re.compile(r'^([A-Za-z_]\w*)\s*\((.*)\)$')
NUM = re.compile(r'^\(?\s*(\d+)\s*\)?$')
CMP = re.compile(r'(\w+)\s*==\s*(-?\d+)')

IGNORE = {'MSG_WND_DSP', 'MSG_WND_CLS', 'MESSAGE_REF'}

# Exact names of flow functions whose first argument is a message/selection index.
# A regex like ^SEL\w*$ would also catch SEL_DEFKEY (a key-code argument) and
# ^MSG\w*$ would catch MSG_TREE_* (scene-graph calls); both produced bogus
# references, so the list is explicit.
MSG_FUNCS = {
    'MSG', 'MSG_MIND', 'MSG_TUTORIAL', 'MSG_DEVIL', 'MSG_PERFORMANCE',
    'MSG_SYSTEM', 'MSG_TRIVIA', 'SELECT_TEXT', 'SELECT_REFUSE_TEXT',
    'SELECT_FRIEND',
}
SEL_FUNCS = {
    'SEL', 'SEL_GENERIC', 'SEL_GENERIC_NOT_HELP', 'SEL_GENERIC_NOT_CANCEL',
    'SEL_GENERIC_EX', 'SEL_HERO',
}


def load_names(hpath):
    names = {}
    try:
        with open(hpath, encoding='utf-8') as fh:
            for line in fh:
                m = HDR.match(line.strip())
                if m:
                    names[int(m.group(2))] = m.group(1)
    except Exception:
        return None
    return names


class Parser:
    def __init__(self, lines, valid):
        self.lines = lines
        self.i = 0
        self.valid = valid
        self.dyn = []
        self.var_msg = {}      # var -> plain numeric value it was assigned
        self.var_sel = {}      # var -> selection index it holds (from SEL only)

    # ---------------------------------------------------------------- helpers
    def peek(self):
        return self.lines[self.i].strip() if self.i < len(self.lines) else None

    def note_dyn(self, cond):
        if cond not in self.dyn:
            self.dyn.append(cond)

    def sel_index(self, arg):
        """Resolve a SEL argument to its message index.

        Only a literal, or a variable that we positively know holds a selection
        result, may be used. A plain variable (e.g. MSG(sVar1, 0)) is *not* a
        message index -- sVar1 holds a value chosen at runtime elsewhere.
        """
        arg = arg.strip()
        m = NUM.match(arg)
        if m:
            return int(m.group(1)), True
        if self.var_sel.get(arg) is not None:
            return self.var_sel[arg], True
        return None, False

    # ------------------------------------------------------------------ parse
    def parse_block(self, stop_on_brace):
        """Parse statements until '}' (if stop_on_brace) or until the buffer ends."""
        items = []
        while self.i < len(self.lines):
            s = self.peek()
            if s is None:
                break
            if s == '' or s.startswith('//'):
                self.i += 1
                continue
            if s == '}':
                self.i += 1
                if stop_on_brace:
                    return items
                continue
            if s == '{':
                self.i += 1
                continue
            if s == 'return;' or s == 'else':
                self.i += 1
                continue
            # a procedure header ends the current body
            if not stop_on_brace and re.match(
                    r'^(void|int|float|bool|string)\s+\S+\s*\(.*\)\s*$', s):
                return items

            if IF_LINE.match(s) or ELSEIF_LINE.match(s):
                items.extend(self.parse_if_chain())
                continue

            self._last_item = None
            self.parse_statement(s)
            if self._last_item is not None:
                items.append(self._last_item)
                self._last_item = None
            self.i += 1
        return items

    _last_item = None

    def parse_statement(self, s):
        s = s.strip()
        if s.endswith(';'):
            s = s[:-1].rstrip()          # CALL insists on ')' at the end

        m = VAR_EQ.match(s)
        if m:
            var, rhs = m.group(1), m.group(2).strip()
            if rhs.endswith(';'):
                rhs = rhs[:-1].rstrip()
            c = CALL.match(rhs)
            if c and c.group(1) in SEL_FUNCS:
                idx, ok = self.sel_index(c.group(2).split(',')[0])
                if ok:
                    self.var_sel[var] = idx
                    self._last_item = {'sel': idx}
                else:
                    self.note_dyn('SEL(' + c.group(2) + ')')
                return
            n = NUM.match(rhs)
            if n:
                self.var_msg[var] = int(n.group(1))
            else:
                # reassigned to something we cannot track: forget any old mapping
                self.var_sel.pop(var, None)
            return

        c = CALL.match(s)
        if not c:
            return
        fn, argstr = c.group(1), c.group(2)
        if fn in IGNORE:
            return
        if fn in SEL_FUNCS:
            idx, ok = self.sel_index(argstr.split(',')[0])
            if ok:
                self._last_item = {'sel': idx}
            else:
                self.note_dyn('SEL(' + argstr + ')')
            return
        if fn in MSG_FUNCS:
            idx, ok = self.sel_index(argstr.split(',')[0])
            if ok:
                self._last_item = idx
            else:
                self.note_dyn(fn + '(' + argstr + ')')

    def parse_if_chain(self):
        """Parse if / else-if* / else? into one cond item.

        Every branch's contents must be parsed *before* the item is built: a
        nested `v = SEL(m)` inside a branch overwrites v, so the mapping a
        condition tests has to be read as early as possible.
        """
        item = {'cond': '', 'var': None, 'values': [], 'varMsg': None,
                'branches': []}
        conds = []

        # --- the leading `if (cond)` ---
        s = self.peek()
        m = IF_LINE.match(s) or ELSEIF_LINE.match(s)
        if not m:
            return []
        cond = m.group(1).strip()
        self.i += 1

        # Which selection feeds this chain? It must be read NOW: a branch body
        # commonly does `v = SEL(...)` again, overwriting v before we get here.
        cm0 = CMP.search(cond)
        if cm0:
            item['var'] = cm0.group(1)
            item['varMsg'] = self.var_sel.get(item['var'])

        # --- collect the whole chain, parsing bodies as we go ---
        while True:
            while self.peek() == '{':
                self.i += 1
            items = self.parse_block(stop_on_brace=True)

            # collapse an else-if whose body is identical to the previous
            # branch (the decompiler emits one per fall-through condition)
            if item['branches'] and items == item['branches'][-1]:
                conds[-1] = conds[-1] + ' / ' + cond
            else:
                conds.append(cond)
                item['branches'].append(items)

            nxt = self.peek()
            m2 = ELSEIF_LINE.match(nxt) if nxt else None
            if m2:
                cond = m2.group(1).strip()
                self.i += 1
                continue

            if nxt == 'else':
                self.i += 1
                while self.peek() == '{':
                    self.i += 1
                if self.peek() == '}':
                    self.i += 1          # empty else: nothing extra to show
                else:
                    els = self.parse_block(stop_on_brace=True)
                    if not (item['branches'] and els == item['branches'][-1]):
                        conds.append('else')
                        item['branches'].append(els)
            break

        item['cond'] = ' / '.join(conds)
        # one value entry per *branch*: a run of collapsed conditions shares the
        # branch index of its first condition, and a trailing `else` is null.
        val_by_cond = [(lambda mm: int(mm.group(2)) if mm else None)(CMP.search(c))
                       for c in conds]
        flat = [c for grp in conds for c in grp.split(' / ')]
        val_by_flat = [(lambda mm: int(mm.group(2)) if mm else None)(CMP.search(c))
                       for c in flat]
        item['values'] = []
        pos = 0
        for grp in conds:
            first = grp.split(' / ')[0]
            if first == 'else':
                item['values'].append(None)
            else:
                item['values'].append(val_by_flat[pos])
            pos += len(grp.split(' / '))

        if item['var'] is None or item['varMsg'] is None:
            self.note_dyn(item['cond'])

        return [item]


def main():
    if not os.path.isdir(FLOW):
        sys.exit('missing ' + FLOW)

    scenes = {}
    n_flow = 0
    n_choice = 0
    n_dyn = 0

    flow_files = []
    for dp, _d, ns in os.walk(FLOW):
        for n in ns:
            if n.endswith('.flow'):
                flow_files.append(os.path.join(dp, n))
    flow_files.sort()
    print('flow files:', len(flow_files))

    for fp in flow_files:
        rel = os.path.relpath(fp, FLOW)
        src = rel[:-5]
        hpath = os.path.join(DEC, src + '.msg.h')
        if not os.path.exists(hpath):
            continue
        names = load_names(hpath)
        if not names:
            continue
        n_flow += 1

        with open(fp, encoding='utf-8') as fh:
            lines = fh.read().split('\n')

        p = Parser(lines, set(names))
        # skip the header / imports / variable declarations; start at the first
        # procedure declaration and concatenate all procedures in order
        seq = []
        for idx, ln in enumerate(lines):
            if re.match(r'^void\s+\S+\s*\(.*\)\s*$', ln.strip()):
                p.i = idx + 1
                if p.peek() == '{':
                    p.i += 1
                seq.extend(p.parse_block(stop_on_brace=True))

        has_choice = any(isinstance(x, dict) and 'cond' in x for x in seq)
        if not seq and not p.dyn:
            continue
        if has_choice:
            n_choice += 1
        if p.dyn:
            n_dyn += 1

        scenes[src] = {'seq': seq, 'dyn': p.dyn}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(scenes, fh, ensure_ascii=False, separators=(',', ':'))

    print('scenes with timeline :', len(scenes))
    print('scenes with choices  :', n_choice)
    print('scenes with dynamic  :', n_dyn)
    print('output               : {:.1f} MB'.format(os.path.getsize(OUT) / 1048576))


if __name__ == '__main__':
    main()
