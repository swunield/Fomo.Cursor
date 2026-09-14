# -*- coding: utf-8 -*-
from pathlib import Path

import paramiko

kv = {}
for line in Path("Server.conf").read_text(encoding="utf-8").splitlines():
    if ":" not in line:
        continue
    k, v = line.split(":", 1)
    kv[k.strip()] = v.strip()

remote = r"""
python3 - <<'PY'
import json, os, glob
root = '/opt/Fomo'
print('=== files ===')
for pat in ['*_last_result.json', '*_holdings_by_token.json']:
    paths = sorted(glob.glob(os.path.join(root, pat)))
    print(pat, len(paths))
    for p in paths:
        print(' ', os.path.basename(p), os.path.getsize(p))
print('trades files', len(glob.glob(os.path.join(root, 'fomo_token_trades/*.json'))))

print('=== TACZ search in last_result ===')
addr_hits = []
for p in sorted(glob.glob(os.path.join(root, '*_last_result.json'))):
    with open(p, encoding='utf-8') as f:
        data = json.load(f)
    rows = data.get('rows') or []
    found = [r for r in rows if str(r.get('名称') or '').upper() == 'TACZ' or 'tacz' in str(r.get('名称') or '').lower()]
    print(os.path.basename(p), 'rows', len(rows), 'TACZ', len(found), 'generatedAt', data.get('generatedAt') or data.get('updatedAt'), 'board', data.get('board'))
    for r in found:
        holders = r.get('holders') or []
        print('  name', r.get('名称'), 'addr', r.get('合约地址'), 'count', r.get('持仓人数'), 'holders_len', len(holders))
        print('  holder names:')
        for h in holders:
            print('   ', f"{h.get('rank')}.{h.get('name')} handle={h.get('handle')} uid={h.get('uid')} trade={h.get('tradeId')} amt={h.get('amount')} val={h.get('value')} upd={h.get('tradeUpdatedAt')}")
        addr_hits.append(r.get('合约地址'))

print('=== TACZ search in holdings json ===')
for p in sorted(glob.glob(os.path.join(root, '*_holdings_by_token.json'))):
    with open(p, encoding='utf-8') as f:
        data = json.load(f)
    rows = data if isinstance(data, list) else (data.get('rows') or [])
    found = [r for r in rows if str(r.get('名称') or '').upper() == 'TACZ']
    print(os.path.basename(p), 'TACZ', len(found))
    for r in found:
        print('  count', r.get('持仓人数'), 'addr', r.get('合约地址'))

addrs = sorted({a for a in addr_hits if a})
print('=== unique TACZ addrs', addrs)
for addr in addrs:
    key = addr.lower()
    path = os.path.join(root, 'fomo_token_trades', f'{key}.json')
    print('chart cache', os.path.basename(path), 'exists', os.path.isfile(path), 'size', os.path.getsize(path) if os.path.isfile(path) else 0)
    if not os.path.isfile(path):
        continue
    with open(path, encoding='utf-8') as f:
        cache = json.load(f)
    traders = cache.get('traders') or {}
    series = cache.get('series') or []
    last = series[-1] if series else None
    print('  lastFetchedAt', cache.get('lastFetchedAt'))
    print('  traders', len(traders), 'series', len(series), 'last_holders', (last or {}).get('holders'), 'last_amount', (last or {}).get('amount'), 'last_t', (last or {}).get('t'))
    print('  stats', cache.get('stats'))
    print('  trader details:')
    for uid, t in traders.items():
        trades = t.get('trades') or {}
        closed = [tid for tid, tr in trades.items() if tr.get('closedAt')]
        open_ = [tid for tid, tr in trades.items() if not tr.get('closedAt')]
        print(f"    {uid} handle={t.get('handle')} name={t.get('displayName')} trades={len(trades)} open={len(open_)} closed={len(closed)}")
        for tid, tr in trades.items():
            print(f"      trade {tid} closedAt={tr.get('closedAt')} updatedAt={tr.get('updatedAt')} swaps={len(tr.get('swaps') or [])} transfers={len(tr.get('transfers') or [])}")
PY
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    kv["Host"],
    username=kv["User"],
    password=kv["Password"],
    timeout=20,
    look_for_keys=False,
    allow_agent=False,
)
stdin, stdout, stderr = client.exec_command(remote, timeout=90)
out = stdout.read().decode("utf-8", "replace")
err = stderr.read().decode("utf-8", "replace")
code = stdout.channel.recv_exit_status()
out_path = Path("tmp_tacz_inspect.txt")
out_path.write_text(out + (("\nSTDERR:\n" + err) if err.strip() else "") + f"\nexit {code}\n", encoding="utf-8")
print(f"wrote {out_path} chars={len(out)} exit={code}")
client.close()
