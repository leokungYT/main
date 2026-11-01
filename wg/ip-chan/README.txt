โยนไฟล์ .conf WireGuard ของ key ชุด "chan" ลงโฟลเดอร์นี้
หรือแยกเป็นโฟลเดอร์ย่อยต่อบัญชีเมล เช่น:
    wg/ip-chan/main-1/   -> บัญชีเมล 1
    wg/ip-chan/main-2/   -> บัญชีเมล 2
    wg/ip-chan/main-3/   -> บัญชีเมล 3

สลับใช้ด้วย configmain.json:
    "wg_profile": "ip-chan"           -> ใช้ทั้งโฟลเดอร์ ip-chan
    "wg_profile": "ip-chan/main-1"    -> ใช้เฉพาะโฟลเดอร์ย่อย main-1
    "wg_profile": "ip-chan/main-2"    -> สลับไป main-2

ว่าง "" = ใช้ wg_dir เดิม (ค่าปัจจุบัน: wg)

กฎ: 1 โฟลเดอร์ (รวมโฟลเดอร์ย่อย) = 1 บัญชีเมล
    ห้ามผสม keypair จากหลายบัญชีในโฟลเดอร์เดียวกัน
