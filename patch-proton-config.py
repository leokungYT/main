"""patch-proton-config.py - patch configmain.json for Proton per-emu mode
- disable wg_auto_gen (otherwise bot warns PresharedKey - Proton conf incompatible with Windscribe wg_gen)
- tune timeout/MTU/keepalive for Proton latency (ping Thailand->JP/SG ~150-250ms)

HOW TO USE:
  cd C:\\Users\\t\\Desktop\\main
  git pull
  python patch-proton-config.py
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(SCRIPT_DIR, "configmain.json")


def main():
    if not os.path.exists(CFG):
        print(f"[ERR] not found: {CFG}")
        return 1

    with open(CFG, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    changed = []
    patches = {
        "wg_auto_gen": 0,
        "wg_regen_every_min": 0,
        "wg_clear_on_start": 0,
        "wg_profile_clear_on_start": 0,
        "black_screen_timeout": 25,
        "wg_mtu": 1420,
        "wg_keepalive": 15,
        "wg_net_recover_max": 20,
        "login_loop_delay": 0.3,
    }

    for k, v in patches.items():
        old = cfg.get(k)
        if old != v:
            cfg[k] = v
            changed.append(f"  {k}: {old} -> {v}")

    if not changed:
        print("[OK] configmain.json: no changes (patches already applied)")
        return 0

    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

    print("[OK] patched configmain.json:")
    for line in changed:
        print(line)
    print()
    print("[NEXT] close bot -> restart to apply new config")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
