"""
xml_to_api.py — reverse direction of api_to_xml.py

Scan a folder of _LINE_COCOS_PREF_KEY.xml files, extract udid + LF_AC from each,
and import them into api/creds.json.

Two modes:
    default  : for each XML, call lgr_api.collect_account(udid, lf_ac) to hit the
               live API, get the real rsn + guestCookie + ruby/coin/level/ticket,
               and merge atomically into creds.json via lgr_api.update_creds.
    --no-login : skip the API call; write a provisional entry keyed as
                 'xml_<first8-of-udid>' with just udid + LF_AC + source filename.
                 Useful for offline bulk import; run with login later to canonicalize.

Usage:
    py xml_to_api.py                            # default: scan ../input-id, live login each
    py xml_to_api.py --src ../input-id --no-login
    py xml_to_api.py --src ../backup-id --dest creds.json --overwrite
    py xml_to_api.py --only Lelouch+-norandom408dc476_LINE_COCOS_PREF_KEY.xml
"""

import argparse
import glob
import io
import json
import os
import re
import sys
import time
import traceback

# force UTF-8 stdout so Thai filenames don't crash on Windows cp1252 console
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

# make lgr_api importable regardless of cwd
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


UDID_RE = re.compile(r'_DEVICE_UUID_KEY">([^<]+)</string>')
ENC_RE  = re.compile(r'_ENC_LF_AC_KEY">(.*?)</string>', re.S)
NAT_RE  = re.compile(r'USER_NATION_CODE">([^<]+)</string>')


def parse_xml(path: str) -> dict | None:
    """Return {'udid','LF_AC','nation'} or None if the file isn't a valid pref XML."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except OSError:
        return None

    m_udid = UDID_RE.search(txt)
    m_enc  = ENC_RE.search(txt)
    if not (m_udid and m_enc):
        return None

    udid = m_udid.group(1).strip()
    # unwrap the FastXmlSerializer chunking: strip '&#10;', whitespace, any stray newlines
    lf_ac = m_enc.group(1).replace("&#10;", "").replace("\n", "").replace("\r", "").strip()
    nation = (NAT_RE.search(txt).group(1).strip() if NAT_RE.search(txt) else "TH")

    if len(udid) != 32 or not lf_ac:
        return None
    return {"udid": udid, "LF_AC": lf_ac, "nation": nation}


def load_creds_safe(path: str) -> dict:
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main() -> int:
    repo_root = os.path.dirname(HERE)
    default_src = os.path.join(repo_root, "input-id")
    default_dest = os.path.join(HERE, "creds.json")

    ap = argparse.ArgumentParser(description="Import _LINE_COCOS_PREF_KEY.xml files into creds.json")
    ap.add_argument("--src", default=default_src,
                    help=f"source folder containing XML files (default: {default_src})")
    ap.add_argument("--dest", default=default_dest,
                    help=f"target creds.json (default: {default_dest})")
    ap.add_argument("--pattern", default="*_LINE_COCOS_PREF_KEY*.xml",
                    help="glob pattern for XMLs (default: *_LINE_COCOS_PREF_KEY*.xml)")
    ap.add_argument("--only", default="",
                    help="comma-separated basename whitelist")
    ap.add_argument("--no-login", action="store_true",
                    help="skip API login — write provisional entry only")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace existing creds entry for the same rsn")
    ap.add_argument("--rate", type=float, default=0.5,
                    help="seconds to sleep between API calls (default: 0.5)")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N files (0 = all)")
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        print(f"[error] source folder not found: {args.src}")
        return 2

    files = sorted(glob.glob(os.path.join(args.src, args.pattern)))
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        files = [p for p in files if os.path.basename(p) in wanted]
    if args.limit:
        files = files[:args.limit]

    if not files:
        print(f"[info] no XML files matched in {args.src}")
        return 0

    print(f"[src]   {args.src}")
    print(f"[dest]  {args.dest}")
    print(f"[mode]  {'offline (no-login)' if args.no_login else 'live-login via lgr_api.collect_account'}")
    print(f"[files] {len(files)}")

    # live-login path needs lgr_api
    collect = update = None
    if not args.no_login:
        try:
            import lgr_api
        except ImportError:
            # repo keeps lgr_api as compiled .pyc only — load it directly
            import importlib.util, importlib.machinery
            pyc_dir = os.path.join(HERE, "__pycache__")
            pyc = None
            if os.path.isdir(pyc_dir):
                for n in sorted(os.listdir(pyc_dir)):
                    if n.startswith("lgr_api.") and n.endswith(".pyc"):
                        pyc = os.path.join(pyc_dir, n); break
            if not pyc:
                print("[error] lgr_api.py not found and no lgr_api*.pyc under api/__pycache__")
                print("        re-run with --no-login or restore api/lgr_api.py")
                return 2
            loader = importlib.machinery.SourcelessFileLoader("lgr_api", pyc)
            spec = importlib.util.spec_from_loader("lgr_api", loader)
            lgr_api = importlib.util.module_from_spec(spec)
            sys.modules["lgr_api"] = lgr_api
            try:
                loader.exec_module(lgr_api)
            except Exception as e:
                print(f"[error] loading {pyc}: {e}")
                return 2
        try:
            collect = lgr_api.collect_account
            update  = lgr_api.update_creds
        except AttributeError as e:
            print(f"[error] lgr_api missing expected symbol: {e}")
            return 2

    existing = load_creds_safe(args.dest)
    existing_rsns = set(existing.keys())

    imported = skipped_dupe = parse_fail = login_fail = 0

    def _flush_offline():
        if not args.no_login:
            return
        os.makedirs(os.path.dirname(args.dest) or ".", exist_ok=True)
        tmp = args.dest + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        os.replace(tmp, args.dest)

    for i, path in enumerate(files, 1):
        base = os.path.basename(path)
        info = parse_xml(path)
        if not info:
            print(f"  [{i}/{len(files)}] {base}  -> parse-fail")
            parse_fail += 1
            continue

        if args.no_login:
            key = f"xml_{info['udid'][:8]}"
            if key in existing and not args.overwrite:
                print(f"  [{i}/{len(files)}] {base}  -> skip (key {key} exists)")
                skipped_dupe += 1
                continue
            entry = {
                "udid":   info["udid"],
                "LF_AC":  info["LF_AC"],
                "nation": info["nation"],
                "file":   base,
                "source": "xml_import",
            }
            existing[key] = entry
            print(f"  [{i}/{len(files)}] {base}  -> {key}  (offline)")
            imported += 1
            continue

        # live-login branch
        try:
            entry = collect(info["udid"], info["LF_AC"])
        except Exception as e:
            print(f"  [{i}/{len(files)}] {base}  -> login-fail: {e}")
            login_fail += 1
            continue

        if not entry or not isinstance(entry, dict):
            print(f"  [{i}/{len(files)}] {base}  -> login-fail: empty response")
            login_fail += 1
            continue

        rsn = entry.get("rsn") or f"xml_{info['udid'][:8]}"
        if rsn in existing_rsns and not args.overwrite:
            print(f"  [{i}/{len(files)}] {base}  -> skip (rsn {rsn} exists)")
            skipped_dupe += 1
            continue

        entry.setdefault("file", base)
        try:
            update({rsn: entry}, args.dest, True)
        except TypeError:
            # update_creds signature mismatch — fall back to local merge + save
            existing[rsn] = entry
        existing_rsns.add(rsn)
        ruby = entry.get("ruby", "?"); coin = entry.get("coin", "?"); lvl = entry.get("level", "?")
        print(f"  [{i}/{len(files)}] {base}  -> {rsn}  ruby={ruby} coin={coin} lvl={lvl}")
        imported += 1

        if args.rate > 0 and i < len(files):
            time.sleep(args.rate)

    # offline mode: write our local copy out at the end
    _flush_offline()

    print(f"[done]  imported={imported}  skipped-dupe={skipped_dupe}  "
          f"parse-fail={parse_fail}  login-fail={login_fail}")
    return 0 if (parse_fail == 0 and login_fail == 0) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[abort] cancelled (offline state may be partial — rerun will resume non-duplicates)")
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
