# -*- coding: utf-8 -*-
"""Locate the anomalous speaker label 礼司 and compare it with 龙司."""
import os, re, collections

STAGING = r'D:\P5RScriptExtract\_staging\decompiled'
SPEAKER_RE = re.compile(r'^(.*?)\s*\[([^\[\]]*)\]$', re.S)

target_files = []
hits = collections.defaultdict(list)   # label -> [(relfile, msgnames)]
all_names = collections.Counter()

for dirpath, _d, filenames in os.walk(STAGING):
    for fn in filenames:
        if not fn.lower().endswith('.msg'):
            continue
        rel = os.path.relpath(os.path.join(dirpath, fn), STAGING)
        try:
            lines = open(os.path.join(dirpath, fn), encoding='utf-8').read().split('\n')
        except Exception:
            continue
        for ln in lines:
            if not ln.startswith('[msg '):
                continue
            payload = ln[5:].rstrip()
            if payload.endswith(']'):
                payload = payload[:-1]
            m = SPEAKER_RE.match(payload)
            if not m or m.group(1).strip() == '':
                continue
            spk = m.group(2).strip()
            all_names[spk] += 1
            hits[spk].append((rel, m.group(1).strip()))

print('=== exact label 礼司 ===')
for rel, name in hits.get('礼司', []):
    print(f'  {rel}   msgname={name}')
print('  count:', all_names.get('礼司', 0))
print()

print('=== labels containing 礼 ===')
for spk in sorted(all_names, key=lambda s: -all_names[s]):
    if '礼' in spk:
        print(f'  {all_names[spk]:>4}  {spk}')
print()

print('=== counts of the main Phantom Thieves names ===')
for spk in ['龙司', '坂本　龙司', '坂本龙司', '杏', '高卷　杏', '真', '新岛　真',
            '佑介', '喜多川　佑介', '双叶', '佐仓　双叶', '春', '奥村　春',
            '摩尔加纳', '明智', '明智　吾郎', '霞', '芳泽　霞', '堇', '芳泽　堇']:
    print(f'  {all_names.get(spk, 0):>7}  {spk}')
print()

# one-character-difference neighbours of key names
def near(a, b):
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(b)):
        if b[:i] + b[i+1:] == a:
            return True
    return False

print('=== labels within 1 character of a main character name ===')
keys = ['龙司', '坂本　龙司', '杏', '高卷　杏', '真', '新岛　真', '佑介',
        '喜多川　佑介', '双叶', '佐仓　双叶', '春', '奥村　春', '摩尔加纳',
        '明智', '明智　吾朗', '霞', '芳泽　霞']
seen = set()
for spk in all_names:
    for k in keys:
        if spk != k and near(spk, k) and len(spk) <= 8:
            if (spk, k) not in seen:
                seen.add((spk, k))
                print(f'  {all_names[spk]:>6}  {spk!r}   ~   {k!r}')
