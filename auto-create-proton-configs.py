"""auto-create-proton-configs.py - auto-generate ProtonVPN WG configs via browser

ใช้ Playwright เปิดเบราว์เซอร์ให้ user login ด้วยตัวเอง (ไม่เก็บ password)
แล้วคลิก Create -> grok form -> Download ซ้ำ ๆ จนครบ N ไฟล์

ติดตั้ง (ครั้งเดียว):
  pip install playwright
  playwright install chromium

ใช้:
  python auto-create-proton-configs.py --count 15 --out proton-configs

ขั้นตอน:
  1. script เปิดเบราว์เซอร์ Chromium
  2. ไปที่ https://account.proton.me/vpn/WireGuard
  3. ให้ user login เอง (ปลอดภัย - script ไม่เห็น password)
  4. หลัง login เสร็จ กด Enter ใน terminal
  5. script คลิก Create N รอบ: ตั้งชื่อ lgr-01..lgr-N, Android, Moderate NAT on, VPN Accel on, Download
  6. ไฟล์ .conf จะ save ลงโฟลเดอร์ out

หมายเหตุ:
  - selector ของ Proton UI อาจเปลี่ยน -> script พัง -> แก้ selector ตามข้างล่าง
  - 15 ไฟล์ใช้เวลาประมาณ 3-5 นาที
  - ถ้า Proton ขึ้น captcha/2FA -> หยุด script ให้ user ทำเอง
  - server picker: script ไม่เลือกแบบ specific -> ใช้ "Fastest" (Proton จะหมุนให้)
"""
import argparse
import asyncio
import os
import sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[ERR] ยังไม่ได้ติดตั้ง playwright - รัน:")
    print("    pip install playwright")
    print("    playwright install chromium")
    sys.exit(2)


COUNTRIES = ["Japan", "Singapore", "Hong Kong", "Taiwan",
             "Vietnam", "Malaysia", "Philippines", "Indonesia"]


async def create_one(page, out_dir, idx, country):
    name = f"lgr-{idx:02d}"
    print(f"[{idx:02d}] สร้าง {name} ({country})...")

    # กด Create (ปุ่มขวาบน)
    try:
        await page.get_by_role("button", name="Create").first.click(timeout=10000)
    except Exception:
        # เผื่อ UI ภาษาไทย
        await page.get_by_role("button", name="สร้าง").first.click(timeout=10000)

    # ชื่ออุปกรณ์
    name_box = page.locator("input[placeholder*='name' i], input[placeholder*='ชื่อ']").first
    await name_box.fill(name, timeout=10000)

    # platform: Android
    try:
        await page.get_by_role("radio", name="Android").check(timeout=5000)
    except Exception:
        await page.get_by_text("Android").first.click()

    # NAT ปานกลาง: ON (toggle)
    # VPN Accelerator: already ON by default
    try:
        # NAT ปานกลาง toggle - ลองหา switch ที่ไม่ได้ check
        toggles = page.locator("button[role='switch']")
        n = await toggles.count()
        for i in range(n):
            label_near = await toggles.nth(i).evaluate(
                "(el) => el.closest('div')?.textContent || ''"
            )
            if "Moderate" in label_near or "ปานกลาง" in label_near:
                checked = await toggles.nth(i).get_attribute("aria-checked")
                if checked != "true":
                    await toggles.nth(i).click()
                break
    except Exception as e:
        print(f"   [WARN] ตั้ง Moderate NAT ไม่สำเร็จ: {e}")

    # เลือกประเทศ (optional)
    try:
        country_sel = page.locator("select, [role='combobox']").first
        await country_sel.click()
        await page.get_by_text(country, exact=True).first.click(timeout=3000)
    except Exception:
        pass   # ปล่อย default "Fastest"

    # กด Create ของ dialog แล้ว download
    async with page.expect_download(timeout=30000) as dl_info:
        try:
            await page.get_by_role("button", name="Create").last.click()
        except Exception:
            await page.get_by_role("button", name="สร้าง").last.click()
        # บาง flow ต้องกด Download เพิ่มหลัง Create
        try:
            await page.get_by_role("button", name="Download").first.click(timeout=5000)
        except Exception:
            pass
    download = await dl_info.value
    target = os.path.join(out_dir, f"{name}.conf")
    await download.save_as(target)
    print(f"   -> {target}")

    # ปิด dialog กลับไปหน้า list
    try:
        await page.get_by_role("button", name="Close").first.click(timeout=3000)
    except Exception:
        await page.keyboard.press("Escape")

    await page.wait_for_timeout(1500)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=15, help="จำนวน config (default 15)")
    ap.add_argument("--out", default="proton-configs", help="โฟลเดอร์ save")
    ap.add_argument("--start", type=int, default=1, help="เริ่มจาก lgr-N")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(accept_downloads=True)
        page = await ctx.new_page()
        await page.goto("https://account.proton.me/vpn/WireGuard")

        print("=" * 60)
        print("[INFO] กรุณา login Proton ในเบราว์เซอร์ที่เพิ่งเปิด")
        print("[INFO] หลัง login เสร็จ (เห็นหน้า WireGuard แล้ว) กด Enter ตรงนี้")
        print("=" * 60)
        try:
            input()
        except EOFError:
            print("[ERR] terminal ไม่รับ input - รัน script นี้จาก cmd ตรง ๆ ไม่ใช่ pipe")
            return 1

        for i in range(args.start, args.start + args.count):
            c = COUNTRIES[(i - 1) % len(COUNTRIES)]
            try:
                await create_one(page, out_dir, i, c)
            except Exception as e:
                print(f"[{i:02d}] FAIL: {e}")
                print(f"   -> หยุดชั่วคราว 10 วิ รอ user แก้ (หรือ Ctrl+C)")
                await page.wait_for_timeout(10000)

        print()
        print("=" * 60)
        print(f"[DONE] สร้างครบ - ไฟล์อยู่ที่ {out_dir}")
        print(f"[DONE] ต่อด้วย: install-proton-wg.bat {out_dir}")
        print("=" * 60)

        print("ปิดเบราว์เซอร์แล้วกด Enter...")
        try: input()
        except Exception: pass
        await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
