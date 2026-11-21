"""
api_to_xml.py — convert api/creds.json entries into Android FastXmlSerializer-format
_LINE_COCOS_PREF_KEY.xml files (byte-identical to ADB-pulled shared_prefs).

Usage:
    py api_to_xml.py                           # default: read api/creds.json, write ../input-id
    py api_to_xml.py --src api/creds.json --out input-id
    py api_to_xml.py --nation TH --prefix conyfly
    py api_to_xml.py --only 40bf66b6,50befc46  # subset by rsn

Format rules (matched against ADB-pulled sample):
- Header:  <?xml version='1.0' encoding='utf-8' standalone='yes' ?>   (single quotes, space before ?>)
- Body:    <map> ... </map>  wrapped by '\n', each child indented 4 spaces
- Long base64 strings (_ENC_LF_AC_KEY) wrapped at 76 chars, '&#10;' between chunks,
  continuation lines flush-left (no indent), last chunk followed by '&#10;' + 4 spaces + </string>
- Line ending: LF, trailing '\n' at end of file
- Fixed fields: _LF_UT_KEY=GUEST, USER_NATION_CODE=<nation>, INPUT_MAX_LENGTH=0,
  LANGUAGE_TYPE_SETTING_KEY=en
- No _PLATFORM_KEY (matches ADB sample)
"""

import argparse
import json
import os
import sys

WRAP = 76
HEADER = "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n"


def wrap_long_string(value: str) -> str:
    """Wrap a long base64 payload the way Android FastXmlSerializer does."""
    if len(value) <= WRAP:
        return value
    chunks = [value[i:i + WRAP] for i in range(0, len(value), WRAP)]
    # FastXmlSerializer stores the whole string on ONE physical line,
    # with '&#10;' as the only separator between 76-char chunks.
    # The final chunk is followed by '&#10;    ' then </string>.
    return "&#10;".join(chunks) + "&#10;    "


def build_xml(udid: str, lf_ac: str, nation: str = "TH") -> str:
    enc = wrap_long_string(lf_ac)
    lines = [
        HEADER.rstrip("\n"),
        "<map>",
        f'    <string name="_ENC_LF_AC_KEY">{enc}</string>',
        '    <string name="_LF_UT_KEY">GUEST</string>',
        f'    <string name="USER_NATION_CODE">{nation}</string>',
        '    <int name="INPUT_MAX_LENGTH" value="0" />',
        '    <string name="LANGUAGE_TYPE_SETTING_KEY">en</string>',
        f'    <string name="_DEVICE_UUID_KEY">{udid}</string>',
        "</map>",
        "",
    ]
    return "\n".join(lines)


def convert(src: str, out_dir: str, nation: str, prefix: str,
            only: set | None = None, overwrite: bool = False) -> tuple[int, int, int]:
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(out_dir, exist_ok=True)
    written = skipped = errored = 0

    for rsn, entry in data.items():
        if only and rsn not in only:
            continue
        try:
            udid = entry["udid"]
            lf_ac = entry["LF_AC"]
        except (KeyError, TypeError):
            print(f"  [skip] {rsn}: missing udid/LF_AC")
            errored += 1
            continue

        name = f"{prefix}-{rsn}_LINE_COCOS_PREF_KEY.xml" if prefix else f"{rsn}_LINE_COCOS_PREF_KEY.xml"
        dst = os.path.join(out_dir, name)
        if os.path.exists(dst) and not overwrite:
            skipped += 1
            continue

        xml = build_xml(udid, lf_ac, nation=nation)
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(xml)
        written += 1

    return written, skipped, errored


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)

    ap = argparse.ArgumentParser(description="Convert api/creds.json to _LINE_COCOS_PREF_KEY.xml files")
    ap.add_argument("--src", default=os.path.join(here, "creds.json"),
                    help="path to creds.json (default: api/creds.json)")
    ap.add_argument("--out", default=os.path.join(repo_root, "input-id"),
                    help="output folder (default: ../input-id)")
    ap.add_argument("--nation", default="TH",
                    help="USER_NATION_CODE value (default: TH)")
    ap.add_argument("--prefix", default="conyfly",
                    help="filename prefix, e.g. 'conyfly' -> conyfly-<rsn>_LINE_COCOS_PREF_KEY.xml")
    ap.add_argument("--only", default="",
                    help="comma-separated rsn whitelist (default: all)")
    ap.add_argument("--overwrite", action="store_true",
                    help="overwrite existing files (default: skip)")
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        print(f"[error] source not found: {args.src}")
        return 2
    if os.path.getsize(args.src) == 0:
        print(f"[error] source is empty: {args.src} (try creds.json.bak)")
        return 2

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    print(f"[src]    {args.src}")
    print(f"[out]    {args.out}")
    print(f"[nation] {args.nation}   [prefix] {args.prefix or '(none)'}")
    if only:
        print(f"[only]   {sorted(only)}")

    w, s, e = convert(args.src, args.out, args.nation, args.prefix,
                      only=only, overwrite=args.overwrite)
    print(f"[done]   written={w}  skipped={s}  errored={e}")
    return 0 if e == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
