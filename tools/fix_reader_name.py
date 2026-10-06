#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix the mistranslated character name in the reader web data.

The Chinese release renders Sakamoto Ryuji's given name as 「礼司」 (Reiji)
instead of 「龙司」 (Ryuji). This corrects:

  * in-text occurrences inside reader/data/scenes/*.json  (the "t" fields)
  * the "dataFixes" audit entry in reader/data/index.json, whose speaker
    mapping named the wrong source label as "礼司" while already mapping it
    to the correct target 坂本　龙司

JSON is edited textually (exact string substitution) so that the surrounding
formatting, key order and escaping produced by the reader generator are
preserved byte-for-byte apart from the corrected characters. Both files are
re-validated with json.loads afterwards.
"""

import json
import os
import sys

# Paths are derived from this file's location so the tools work from any checkout.
# Override with the P5R_ROOT environment variable if needed.
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('P5R_ROOT') or os.path.dirname(_HERE)

READER = os.path.join(ROOT, 'reader')
DATA = os.path.join(READER, 'data')

WRONG = '\u793c\u53f8'          # 礼司
RIGHT = '\u9f99\u53f8'          # 龙司
FULL = '\u5742\u672c\u3000' + RIGHT   # 坂本　龙司


def fix_file(path):
    with open(path, encoding='utf-8') as fh:
        raw = fh.read()

    n = raw.count(WRONG)
    if not n:
        return 0, 0

    new = raw.replace(WRONG, RIGHT)

    # the audit entry named the wrong source label; keep the record truthful
    old_entry = '"from":"' + RIGHT + '","to":"' + FULL + '"'
    good_entry = '"from":"' + WRONG + '","to":"' + FULL + '"'
    audit_fixed = 0
    if old_entry in new:
        new = new.replace(old_entry, good_entry)
        audit_fixed = 1

    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(new)

    # validate
    with open(path, encoding='utf-8') as fh:
        json.load(fh)

    return n, audit_fixed


def main():
    targets = []
    for dirpath, _dirs, names in os.walk(DATA):
        for name in sorted(names):
            if name.endswith('.json'):
                targets.append(os.path.join(dirpath, name))

    total = 0
    for path in targets:
        n, audit = fix_file(path)
        if n:
            rel = os.path.relpath(path, READER)
            print('  {:44} replacements={} auditFixed={}'.format(rel, n, audit))
            total += n

    print()
    print('total replacements:', total)

    # verification: the only remaining occurrence may be the audit record in
    # index.json, which intentionally quotes the wrong source label.
    left = 0
    for path in targets:
        with open(path, encoding='utf-8') as fh:
            raw = fh.read()
        if path.endswith('index.json'):
            try:
                doc = json.loads(raw)
                if 'dataFixes' in doc:
                    without = json.dumps(
                        {k: v for k, v in doc.items() if k != 'dataFixes'},
                        ensure_ascii=False)
                    left += without.count(WRONG)
                    continue
            except Exception:
                pass
        left += raw.count(WRONG)
    print('remaining wrong name in reader data (excluding audit record):', left)

    if os.path.exists(os.path.join(READER, 'index.html')):
        with open(os.path.join(READER, 'index.html'), encoding='utf-8') as fh:
            print('remaining wrong name in index.html:',
                  fh.read().count(WRONG))

    print('RESULT:', 'OK' if left == 0 else 'FAILED')
    return 0 if left == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
