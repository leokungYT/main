"""
login_all.py — for every decrypted account in creds.json, hit /v12.4/login + /v12.4/home
and record result. Uses the shared `cc` cookie captured once from MITM.
"""
import argparse, base64, gzip, io, json, os, re, sys, time
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

BASE = 'https://rangers-api.line-apps.com/v12.4'
# shared cc cookie — same value works for all accounts
CC = os.environ.get('LGR_CC',
    'Qjb8LfG1/gFLI16zjGlVAi4LijycBPDIpxg65x5jrGN2SH+I6GCQb9W+qSN4FRG36jnfkmfpqj/dNOiXOuS2qp0fCrTL3Ns1MTAV4XE08L8F7Xf5M4+WXKWXNBWRA1aIjThTGpfXaE128kPbRlvyOg==')


def base_headers() -> dict:
    return {
        'app-version': 'LGRGS/12.4.2;android/12',
        'uselgc': 'true',
        'nation-code': 'TH',
        'accept-language': 'en',
        'user-agent': 'LGRGS/12.4.2 (Linux; U; Android 12; en-US; SM-A546E Build/V417IR)',
        'x-linegame-mcc': '000',
        'x-linegame-mnc': '00',
        'accept-encoding': 'gzip',
    }


def login(session: requests.Session, udid: str, guest: str, timeout: float = 15) -> tuple[int, str | None]:
    """Hit /login, return (status, new_LF_AC_or_None)."""
    h = base_headers()
    h['x-linegame-timestamp'] = str(int(time.time()*1000))
    h['cookie'] = f'cc={CC}; udid={udid}; guestCookie={guest}; LF_AC={guest}'
    r = session.get(f'{BASE}/login', headers=h, timeout=timeout)
    if r.status_code != 200:
        return r.status_code, None
    sc = r.headers.get('set-cookie', '')
    m = re.search(r'LF_AC=([^;]+)', sc)
    return 200, (m.group(1) if m else guest)


def home(session: requests.Session, udid: str, guest: str, lfac: str, timeout: float = 15) -> tuple[int, dict | str | None]:
    h = base_headers()
    h['x-linegame-timestamp'] = str(int(time.time()*1000))
    h['cookie'] = f'cc={CC}; udid={udid}; guestCookie={guest}; LF_AC={lfac}'
    r = session.get(f'{BASE}/home', headers=h, timeout=timeout)
    if r.status_code != 200:
        return r.status_code, None
    try:
        return 200, r.json()
    except Exception as e:
        return 200, f'JSON_ERR: {e}; body[:80]={r.text[:80]!r}'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='api/creds.json')
    ap.add_argument('--out', default='api/creds.json')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--rate', type=float, default=0.3, help='sleep between accounts')
    ap.add_argument('--home', action='store_true', help='also fetch /home')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    with open(args.src, 'r', encoding='utf-8') as f:
        data = json.load(f)
    accounts = [(k, v) for k, v in data.items() if v.get('decrypted')]
    if args.limit:
        accounts = accounts[:args.limit]
    print(f'[*] testing {len(accounts)} accounts')

    ok_login = ok_home = fail = 0
    session = requests.Session()

    for i, (key, e) in enumerate(accounts, 1):
        udid, guest = e['udid'], e['guestCookie']
        try:
            st, new_lfac = login(session, udid, guest)
        except Exception as ex:
            print(f'  [{i}/{len(accounts)}] {key}  LOGIN-EXC {ex}')
            fail += 1
            if args.rate > 0: time.sleep(args.rate)
            continue

        if st != 200:
            print(f'  [{i}/{len(accounts)}] {key}  login-status={st}')
            fail += 1
            if args.rate > 0: time.sleep(args.rate)
            continue

        ok_login += 1
        e['LF_AC'] = new_lfac
        e['lastLoginTs'] = int(time.time())
        info = ''

        if args.home and new_lfac:
            try:
                hst, hdata = home(session, udid, guest, new_lfac)
                if hst == 200 and isinstance(hdata, dict) and 'result' in hdata:
                    rr = hdata['result']
                    ok_home += 1
                    player = rr.get('player', {})
                    e['rsn'] = player.get('mid', e.get('rsn', ''))
                    e['userName'] = player.get('userName', '')
                    e['ruby'] = rr.get('rubyBalance', {}).get('total', 0)
                    info = f' home ruby={e["ruby"]} user={e["userName"]} mid={e["rsn"]}'
                elif isinstance(hdata, str):
                    info = f' home-{hdata[:80]}'
                else:
                    info = f' home-status={hst} hdata-type={type(hdata).__name__}'
            except Exception as ex:
                info = f' home-exc={ex}'

        print(f'  [{i}/{len(accounts)}] {key}  login-OK  LF_AC[:40]={new_lfac[:40]}...{info}')

        if args.rate > 0 and i < len(accounts):
            time.sleep(args.rate)

    print(f'[done]  login-OK={ok_login}  home-OK={ok_home}  fail={fail}')

    if not args.dry_run:
        tmp = args.out + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, args.out)
        print(f'[saved] {args.out}')
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
