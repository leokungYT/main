"""install-proton-wg.py - install ProtonVPN WireGuard configs as per-emulator mode

HOW TO USE:
  1. subscribe ProtonVPN Plus
  2. go to https://account.proton.me/vpn/WireGuard
  3. download 15 WG configs (any country, no need TH)
     - server name: anything, e.g. lgr1, lgr2, lgr3, ...
     - NAT type: "Moderate NAT" (best for games)
     - VPN Accelerator: ON
  4. put all .conf files in one folder (e.g. proton-configs/)
  5. run: python install-proton-wg.py proton-configs/

Distributes 15 configs into main-1..main-5 (3 files/sub)
Patches configmain.json: host VPN off + per-emu WG on (auto)
"""
import glob
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WG_DIR = os.path.join(SCRIPT_DIR, "wg", "ip-chan")
CFG = os.path.join(SCRIPT_DIR, "configmain.json")


def main():
    if len(sys.argv) < 2:
        print("usage: python install-proton-wg.py <path-to-proton-configs-folder>")
        print("    or python install-proton-wg.py <single-config-file.conf>")
        return 1

    src = sys.argv[1]
    if os.path.isfile(src):
        confs = [src]
    elif os.path.isdir(src):
        confs = sorted(glob.glob(os.path.join(src, "*.conf")))
    else:
        print(f"[ERR] not found: {src}")
        return 1

    if not confs:
        print(f"[ERR] no .conf files in {src}")
        return 1

    print(f"[INFO] found {len(confs)} .conf files")

    # distribute into main-1..main-5 (3 files/sub)
    PER_SUB = 3
    N_SUB = 5
    subs = [os.path.join(WG_DIR, f"main-{i+1}") for i in range(N_SUB)]

    for sub in subs:
        os.makedirs(sub, exist_ok=True)
        # clear old files
        for f in glob.glob(os.path.join(sub, "*.conf")):
            os.remove(f)
        print(f"[CLEAN] {sub}")

    # distribute + strip IPv6 (MuMu Android WG is unstable with IPv6)
    def _strip_ipv6(text):
        out = []
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("Address") or s.startswith("DNS") or s.startswith("AllowedIPs"):
                k, _, v = s.partition("=")
                parts = [p.strip() for p in v.split(",") if ":" not in p and p.strip()]
                if parts:
                    out.append(f"{k.strip()} = {', '.join(parts)}")
                continue
            # drop IPv6 Endpoint fallback (commented out anyway)
            if s.startswith("# Endpoint = ["):
                continue
            out.append(line)
        return "\n".join(out) + "\n"

    warned_free = False
    for i, conf in enumerate(confs):
        sub_idx = i % N_SUB
        target = os.path.join(subs[sub_idx], f"proton-{i+1:02d}.conf")
        try:
            with open(conf, "r", encoding="utf-8") as f:
                txt = f.read()
            if "FREE" in txt and not warned_free:
                print("[WARN] FREE server detected - these are shared with all Proton Free users worldwide")
                print("       recreate with Plus server (no 'FREE' in name)")
                warned_free = True
            txt = _strip_ipv6(txt)
            with open(target, "w", encoding="utf-8") as f:
                f.write(txt)
        except Exception as e:
            print(f"[ERR] read/write {conf} failed: {e}")
            continue
        print(f"[COPY] {os.path.basename(conf)} -> main-{sub_idx+1}/proton-{i+1:02d}.conf (IPv4 only)")

    # patch configmain.json
    if os.path.exists(CFG):
        with open(CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # Proton per-emu mode
        cfg["use_host_vpn"] = 0
        cfg["wg_enabled"] = 1
        cfg["wg_profile"] = [f"ip-chan/main-{i+1}" for i in range(N_SUB)]
        cfg["wg_clear_on_start"] = 0
        cfg["wg_profile_clear_on_start"] = 0
        cfg["wg_hard_reset_on_start"] = 1
        # use minimum per sub as wg_per_machine - don't let bot try to generate more (Proton conf incompatible with wg_gen)
        min_per_sub = min(len(os.listdir(sub)) for sub in subs) if all(os.listdir(s) for s in subs) else 1
        cfg["wg_per_machine"] = max(1, min_per_sub)
        cfg["wg_auto_gen"] = 0   # disable wg_gen (Windscribe generator) - Proton conf is not a template
        cfg["wg_regen_every_min"] = 0
        # Latency-friendly tuning for Proton VPN (ping Thailand->JP/SG ~150-250ms)
        cfg["black_screen_timeout"] = int(cfg.get("black_screen_timeout", 8) or 8)
        if cfg["black_screen_timeout"] < 20:
            cfg["black_screen_timeout"] = 25
        cfg["wg_mtu"] = 1420
        cfg["wg_keepalive"] = 15
        cfg["wg_net_recover_max"] = 20
        cfg["login_loop_delay"] = 0.3
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        print(f"[CFG] configmain.json: use_host_vpn=0, wg_profile={cfg['wg_profile']}, wg_per_machine={cfg['wg_per_machine']}")
        print(f"[CFG] + latency tuning: black_screen_timeout=25, mtu=1420, keepalive=15, net_recover_max=20")

    print()
    print("=" * 60)
    print("[DONE] ProtonVPN per-emu mode installed")
    print("=" * 60)
    print("NEXT:")
    print("  1. close Windscribe app (not needed anymore)")
    print("  2. close windscribe_cli_rotator.py (not needed anymore)")
    print("  3. git pull + restart bot")
    print("  4. bot will connect WG per-emu - 15 emu = 15 IP")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
