"""patch-proton-config.py - patch configmain.json สำหรับ Proton per-emu mode
- ปิด wg_auto_gen (ไม่งั้น bot ขึ้น warning PresharedKey เพราะ Proton conf ไม่เข้ากับ wg_gen Windscribe)
- ปรับ timeout/MTU/keepalive ให้รองรับ Proton latency (ping Thai->JP/SG ~150-250ms)

ใช้ยังไง:
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
        print(f"[ERR] ไม่เจอ: {CFG}")
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
        print("[OK] configmain.json: ไม่มีการเปลี่ยนแปลง (patches เคยทำแล้ว)")
        return 0

    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

    print("[OK] patched configmain.json:")
    for line in changed:
        print(line)
    print()
    print("[NEXT] ปิดบอท -> รีสตาร์ท เพื่อให้ config ใหม่ทำงาน")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
