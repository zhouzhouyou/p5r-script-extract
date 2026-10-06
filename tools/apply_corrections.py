#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apply translation corrections to the generated dialogue script (and to the
mirrored .msg staging files).

Corrections are data-driven: edit CORRECTIONS below and re-run.

  礼司 -> 龙司   (U+793C U+53F8  ->  U+9F99 U+53F8)
      The Chinese release misrenders Sakamoto Ryuji's given name as 「礼司」
      (Reiji) instead of 「龙司」 (Ryuji). Both speaker labels and in-text
      references are affected.

Behaviour per .txt script file:
  * the stale per-dialog note "（原始数据中说话人误写作「礼司」，已修正）" is
    replaced by one file-level note at the top, so the note itself no longer
    contradicts the corrected text;
  * every remaining occurrence of the wrong name is corrected;
  * files are rewritten only when their content actually changes.
"""

import os
import sys

# Paths are derived from this file's location so the tools work from any checkout.
# Override with the P5R_ROOT environment variable if needed.
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('P5R_ROOT') or os.path.dirname(_HERE)

SCRIPT_DIR = os.path.join(ROOT, 'P5R_对话脚本')
STAGING_DIR = os.path.join(ROOT, '_staging', 'decompiled')

# (wrong, right, human description)
CORRECTIONS = [
    ('\u793c\u53f8', '\u9f99\u53f8', '坂本龙司的译名误作「礼司」'),
]

STALE_NOTE = '\uff08\u539f\u59cb\u6570\u636e\u4e2d\u8bf4\u8bdd\u4eba\u8bef\u5199\u4f5c\u300c\u793c\u53f8\u300d\uff0c\u5df2\u4fee\u6b63\uff09'


NOTE_MARKER = '\u3010\u8bd1\u540d\u4fee\u6b63\u3011'


def build_note():
    """The single file-level note, built from the original (wrong -> right)
    mapping so that re-running the script is idempotent."""
    parts = ['{0}\u2192{1}\uff08{2}\uff09'.format(w, r, d) for w, r, d in CORRECTIONS]
    return NOTE_MARKER + '\uff1b'.join(parts)


def apply(text):
    """Replace wrong names everywhere except on existing correction notes."""
    lines = text.split('\n')
    counts = {}
    for i, line in enumerate(lines):
        if NOTE_MARKER in line:
            continue
        for wrong, right, _d in CORRECTIONS:
            n = line.count(wrong)
            if n:
                counts[wrong] = counts.get(wrong, 0) + n
                line = line.replace(wrong, right)
        lines[i] = line
    return '\n'.join(lines), counts


def strip_notes(text):
    """Remove every existing correction note so exactly one can be re-added."""
    kept = [ln for ln in text.split('\n') if NOTE_MARKER not in ln]
    return '\n'.join(kept), len(text.split('\n')) - len(kept)


def fix_script_files(verbose=True):
    files_written = 0
    total_text_fixes = 0
    total_notes_removed = 0
    touched = []

    for dirpath, _dirs, names in os.walk(SCRIPT_DIR):
        for name in sorted(names):
            if not name.endswith('.txt'):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8') as fh:
                text = fh.read()

            original = text

            # 1) drop the stale per-dialog notes and any previous file note
            notes = text.count(STALE_NOTE)
            text = text.replace('    ' + STALE_NOTE + '\n', '')
            text = text.replace(STALE_NOTE + '\n', '')
            text = text.replace(STALE_NOTE, '')
            text, removed_notes = strip_notes(text)
            total_notes_removed += notes + removed_notes

            # 2) correct the remaining in-text occurrences
            text, counts = apply(text)
            text_fixes = sum(counts.values())
            total_text_fixes += text_fixes
            had_notes = (notes + removed_notes) > 0

            # 3) re-add a single, correct file-level note when needed
            if text_fixes or had_notes:
                lines = text.split('\n')
                at = 5 if len(lines) > 5 else len(lines)
                lines.insert(at, build_note())
                text = '\n'.join(lines)

            if text != original:
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write(text)
                files_written += 1
                touched.append((os.path.relpath(path, SCRIPT_DIR), text_fixes, notes + removed_notes))

    if verbose:
        for rel, tf, nt in sorted(touched, key=lambda x: -x[1]):
            print('  {:56} text={:<3} notes={}'.format(rel, tf, nt))

    return files_written, total_text_fixes, total_notes_removed


def fix_staging_files():
    total = 0
    files = 0
    for dirpath, _dirs, names in os.walk(STAGING_DIR):
        for name in names:
            if not name.endswith('.msg'):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8') as fh:
                text = fh.read()
            new_text, counts = apply(text)
            if counts:
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write(new_text)
                total += sum(counts.values())
                files += 1
    return files, total


NOTE_MARKER = '\u3010\u8bd1\u540d\u4fee\u6b63\u3011'


def count_wrong(root, exts, skip_notes=True):
    """Count leftover wrong names, ignoring the file-level correction note
    (which intentionally quotes the old name)."""
    total = 0
    per_file = {}
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if not name.lower().endswith(exts):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8') as fh:
                c = 0
                for line in fh:
                    if skip_notes and NOTE_MARKER in line:
                        continue
                    c += line.count(CORRECTIONS[0][0])
            if c:
                per_file[os.path.relpath(path, root)] = c
                total += c
    return total, per_file


def main():
    wrong = CORRECTIONS[0][0]
    right = CORRECTIONS[0][1]

    print('=== 1) readable script ===')
    files, fixes, notes = fix_script_files()
    print('files rewritten   :', files)
    print('in-text fixes     :', fixes)
    print('stale notes fixed :', notes)

    print()
    print('=== 2) staging .msg files ===')
    sfiles, sfix = fix_staging_files()
    print('files rewritten   :', sfiles)
    print('replacements      :', sfix)

    print()
    print('=== 3) verification ===')
    t1, per1 = count_wrong(SCRIPT_DIR, ('.txt',))
    t2, per2 = count_wrong(STAGING_DIR, ('.msg',))
    print('remaining wrong name in script :', t1)
    print('remaining wrong name in staging:', t2)
    for rel, c in per1.items():
        print('   script  {:<55} {}'.format(rel, c))
    for rel, c in per2.items():
        print('   staging {:<55} {}'.format(rel, c))

    ok = (t1 == 0)
    print()
    print('RESULT:', 'OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
