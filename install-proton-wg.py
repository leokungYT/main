"""install-proton-wg.py - ติดตั้ง ProtonVPN WireGuard config เป็น per-emulator mode

ใช้ยังไง:
  1. สมัคร ProtonVPN Plus
  2. เข้า https://account.proton.me/vpn/WireGuard
  3. Download WG config 15 ไฟล์ (country ไหนก็ได้ ไม่ต้อง TH)
     - ตั้งชื่อ server อะไรก็ได้ เช่น lgr1, lgr2, lgr3, ...
     - NAT type: "Moderate NAT" ดีสุดสำหรับเกม
     - VPN Accelerator: เปิด
  4. โยนไฟล์ .conf ทั้งหมดไว้ในโฟลเดอร์ 1 โฟลเดอร์ (เช่น proton-configs/)
  5. รัน: python install-proton-wg.py proton-configs/

จะกระจาย 15 config เป็น main-1 ถึง main-5 (3 ไฟล์/sub)
พร้อมแก้ configmain.json ให้ปิด host VPN + เปิด per-emu WG อัตโนมัติ
"""
import glob
import json
import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WG_DIR = os.path.join(SCRIPT_DIR, "wg", "ip-chan")
CFG = os.path.join(SCRIPT_DIR, "configmain.json")


def main():
    if len(sys.argv) < 2:
        print("ใช้: python install-proton-wg.py <path-to-proton-configs-folder>")
        print("หรือ: python install-proton-wg.py <single-config-file.conf> (ทำ 1 ไฟล์)")
        return 1

    src = sys.argv[1]
    if os.path.isfile(src):
        confs = [src]
    elif os.path.isdir(src):
        confs = sorted(glob.glob(os.path.join(src, "*.conf")))
    else:
        print(f"[ERR] ไม่เจอ: {src}")
        return 1

    if not confs:
        print(f"[ERR] ไม่เจอไฟล์ .conf ใน {src}")
        return 1

    print(f"[INFO] เจอ {len(confs)} ไฟล์ .conf")

    # กระจายเป็น main-1..main-5 (3 ไฟล์/sub)
    PER_SUB = 3
    N_SUB = 5
    subs = [os.path.join(WG_DIR, f"main-{i+1}") for i in range(N_SUB)]

    for sub in subs:
        os.makedirs(sub, exist_ok=True)
        # ล้างของเก่า
        for f in glob.glob(os.path.join(sub, "*.conf")):
            os.remove(f)
        print(f"[CLEAN] {sub}")

    # กระจาย
    for i, conf in enumerate(confs):
        sub_idx = i % N_SUB
        target = os.path.join(subs[sub_idx], f"proton-{i+1:02d}.conf")
        shutil.copy2(conf, target)
        print(f"[COPY] {os.path.basename(conf)} -> main-{sub_idx+1}/proton-{i+1:02d}.conf")

    # แก้ config
    if os.path.exists(CFG):
        with open(CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["use_host_vpn"] = 0
        cfg["wg_enabled"] = 1
        cfg["wg_profile"] = [f"ip-chan/main-{i+1}" for i in range(N_SUB)]
        cfg["wg_clear_on_start"] = 0
        cfg["wg_profile_clear_on_start"] = 0
        cfg["wg_hard_reset_on_start"] = 1
        cfg["wg_per_machine"] = PER_SUB
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        print(f"[CFG] configmain.json: use_host_vpn=0, wg_profile={cfg['wg_profile']}")

    print()
    print("=" * 60)
    print("[DONE] ติดตั้ง ProtonVPN per-emu mode เรียบร้อย")
    print("=" * 60)
    print("ขั้นต่อไป:")
    print("  1. ปิด Windscribe app (ไม่ต้องใช้แล้ว)")
    print("  2. ปิด windscribe_cli_rotator.py (ไม่ต้องใช้แล้ว)")
    print("  3. git pull + รีสตาร์ทบอท")
    print("  4. บอทจะต่อ WG ให้แต่ละ emu แยก - 15 emu = 15 IP")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
