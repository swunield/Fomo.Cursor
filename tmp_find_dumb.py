# -*- coding: utf-8 -*-
"""Find DumbCrayonEater AI holding and try wallet match by amount."""
from deploy.push import connect, run

SCRIPT = r"""
import json, os, glob
uid = '6e51b3ef-54bc-5062-894b-3f06986ac242'
handle_l = 'dumbcrayoneater'

# holdings exports
for name in [
    'fomo_top20_holdings_by_token.json',
    'fomo_7d50_holdings_by_token.json',
    'fomo_24h_holdings_by_token.json',
]:
    p = '/opt/Fomo/' + name
    if not os.path.exists(p):
        print('missing', name)
        continue
    data = json.load(open(p, encoding='utf-8'))
    print('FILE', name, 'top_type', type(data).__name__,
          'keys', list(data)[:12] if isinstance(data, dict) else len(data))

def find_in_holdings(path):
    data = json.load(open(path, encoding='utf-8'))
    # common shapes: {tokens:[{name,address,holders:[...]}]} or list of tokens
    tokens = []
    if isinstance(data, dict):
        if 'tokens' in data:
            tokens = data['tokens']
        elif 'byToken' in data:
            tokens = list(data['byToken'].values()) if isinstance(data['byToken'], dict) else data['byToken']
        else:
            # maybe address -> entry
            sample = next(iter(data.values()), None)
            if isinstance(sample, dict) and ('holders' in sample or '持仓人' in sample or 'name' in sample):
                tokens = list(data.values())
    elif isinstance(data, list):
        tokens = data
    hits = []
    for tok in tokens:
        if not isinstance(tok, dict):
            continue
        name = str(tok.get('name') or tok.get('名称') or tok.get('symbol') or '')
        addr = str(tok.get('address') or tok.get('合约地址') or tok.get('tokenAddress') or '')
        holders = tok.get('holders') or tok.get('holderRows') or tok.get('持仓人') or []
        # holders may be string "9.ogle, 3.xxx"
        if isinstance(holders, str):
            if handle_l in holders.lower():
                hits.append((name, addr, tok))
            continue
        for h in holders:
            if not isinstance(h, dict):
                continue
            hh = (h.get('handle') or h.get('nickname') or h.get('name') or '').lower()
            if handle_l in hh or h.get('userId') == uid or h.get('id') == uid:
                hits.append((name, addr, tok, h))
    return hits

for name in [
    'fomo_top20_holdings_by_token.json',
    'fomo_7d50_holdings_by_token.json',
    'fomo_24h_holdings_by_token.json',
]:
    p = '/opt/Fomo/' + name
    if not os.path.exists(p):
        continue
    hits = find_in_holdings(p)
    print('HITS', name, len(hits))
    for item in hits[:15]:
        print(' ', item[0], item[1][:20] if item[1] else '', '...')
        if len(item) >= 4:
            h = item[3]
            print('   holder', {k: h.get(k) for k in list(h)[:25]})
        else:
            tok = item[2]
            # print AI-related fields
            print('   tok keys', list(tok)[:30])
            for k in ('所有持仓人','最高持仓人','最低持仓人','持仓市值','市值','holdersText','allHolders'):
                if k in tok:
                    print('  ', k, str(tok[k])[:200])

# wallet cache row
wp = '/opt/Fomo/fomo_wallet_links.json'
if os.path.exists(wp):
    d = json.load(open(wp, encoding='utf-8'))
    row = (d.get('traders') or {}).get(uid) or {}
    print('CACHE', row.get('handle'), row.get('status'), row.get('reason'), row.get('holdingReason'))
    print(' wallets', row.get('wallets'))
    # also dump trader summary from resolve side - trades networks
    from fomo_wallet_link import load_traders
    traders = load_traders()
    tr = traders.get(uid)
    if tr:
        print('TRADER swaps', len(tr.get('swaps') or []), 'networks',
              sorted({s.get('network') for s in (tr.get('swaps') or [])}))
        # look for AI symbol/name in swaps
        for s in tr.get('swaps') or []:
            sym = (s.get('symbol') or s.get('tokenName') or s.get('name') or '')
            if str(sym).upper() == 'AI' or 'ai' == str(sym).lower():
                print('SWAP_AI', s)
        # print largest holdings by amount*mcap if present
        bals = tr.get('balances') or tr.get('holdings') or []
        print('balances_n', len(bals))
        # inspect swap tokens that might be AI
        by_tok = {}
        for s in tr.get('swaps') or []:
            t = s.get('token') or ''
            by_tok.setdefault(t, {'n':0,'net':s.get('network'),'sym':s.get('symbol') or s.get('name'),'amt':0})
            by_tok[t]['n'] += 1
        # print top tokens by swap count
        top = sorted(by_tok.items(), key=lambda kv: -kv[1]['n'])[:15]
        for t, info in top:
            print('TOK', info['n'], info['net'], info['sym'], t[:48])
"""


def main() -> None:
    _, client = connect()
    code, out, err = run(
        client,
        "cd /opt/Fomo && .venv/bin/python - <<'PY'\n" + SCRIPT + "\nPY\n",
        timeout=180,
    )
    print(out)
    if err:
        print(err)
    print("exit", code)
    client.close()


if __name__ == "__main__":
    main()
