"""
test_ocr_screen.py - ไฟล์ทดสอบ OCR อ่านตัวเลข/ข้อความทั้งหน้าจอจาก Android Emulator

วิธีใช้:
1. เปิด MuMu Player/Emulator
2. รัน: python test_ocr_screen.py

ต้องติดตั้ง:
- pip install easyocr opencv-python numpy Pillow
"""

import subprocess
import numpy as np
import cv2
from PIL import Image
import time
import os

# ===== สร้างโฟลเดอร์เก็บ output =====
OUTPUT_FOLDER = "ocr_output"
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)
    print(f"✅ สร้างโฟลเดอร์ {OUTPUT_FOLDER}/")

# ===== ใช้ EasyOCR (แม่นยำกว่า Tesseract) =====
import easyocr

# สร้าง reader สำหรับภาษาอังกฤษ (ตัวเลข)
print("กำลังโหลด EasyOCR... (ครั้งแรกอาจช้าหน่อย)")
reader = easyocr.Reader(['en'], gpu=False)  # gpu=False สำหรับ CPU
print("✅ โหลด EasyOCR สำเร็จ!")

def connect_mumu():
    """เชื่อมต่อ MuMu Player โดยสแกน port อัตโนมัติ"""
    print("   กำลังสแกน port MuMu Player...")
    
    # Port ที่ MuMu ใช้ (5555, 5557, 5559, ...)
    mumu_ports = [5555, 5557, 5559, 5561, 5563, 5565, 5567, 5569, 5571, 5573]
    
    connected_devices = []
    
    # Start adb server ก่อน
    try:
        subprocess.run(['adb', 'start-server'], capture_output=True, timeout=5)
        time.sleep(0.5)
    except:
        pass
    
    for port in mumu_ports:
        try:
            result = subprocess.run(
                ['adb', 'connect', f'127.0.0.1:{port}'],
                capture_output=True, 
                text=True, 
                timeout=3
            )
            
            if 'connected' in result.stdout.lower() or 'already connected' in result.stdout.lower():
                print(f"   ✅ เชื่อมต่อ port {port} สำเร็จ")
                connected_devices.append(f'127.0.0.1:{port}')
        except:
            pass
    
    return connected_devices

def get_connected_device():
    """ค้นหา device ที่เชื่อมต่ออยู่"""
    try:
        # ลองเชื่อมต่อ MuMu ก่อน
        mumu_devices = connect_mumu()
        
        # ตรวจสอบ devices ทั้งหมด
        result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split('\n')
        
        for line in lines[1:]:  # ข้ามบรรทัดแรก (List of devices attached)
            if '\tdevice' in line:
                device_serial = line.split('\t')[0]
                return device_serial
        
        # ถ้าไม่เจอจาก adb devices แต่เชื่อมต่อ MuMu ได้
        if mumu_devices:
            return mumu_devices[0]
            
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def capture_screen(device_serial):
    """จับภาพหน้าจอจาก device"""
    try:
        # ใช้ adb exec-out screencap -p
        cmd = ['adb', '-s', device_serial, 'exec-out', 'screencap', '-p']
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        
        if result.returncode == 0 and len(result.stdout) > 0:
            # แปลงเป็น numpy array
            image_data = np.frombuffer(result.stdout, dtype=np.uint8)
            img = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
            return img
        return None
    except Exception as e:
        print(f"Error capturing screen: {e}")
        return None

def ocr_full_screen(img):
    """อ่านข้อความทั้งหน้าจอ - ใช้ EasyOCR"""
    try:
        # ใช้ EasyOCR อ่านทั้งหน้าจอ
        results = reader.readtext(img, detail=0)
        
        if results:
            all_text = ' '.join(results)
            # กรองเอาเฉพาะตัวเลข
            numbers_text = ' '.join([c for c in results if c.isdigit() or c.replace(' ', '').isdigit()])
            return numbers_text, all_text
        
        return "", ""
    except Exception as e:
        print(f"Error OCR: {e}")
        return None, None

def ocr_region(img, x, y, width, height, save_crop=None):
    """อ่านข้อความจากพื้นที่ที่กำหนด - ใช้ EasyOCR"""
    try:
        h, w = img.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x + width)
        y2 = min(h, y + height)
        
        cropped = img[y1:y2, x1:x2]
        
        # บันทึกภาพ crop ถ้าระบุ (ลงโฟลเดอร์ ocr_output)
        if save_crop:
            save_path = os.path.join(OUTPUT_FOLDER, save_crop)
            cv2.imwrite(save_path, cropped)
        
        # ===== ขยายภาพ 3 เท่า (EasyOCR ต้องการภาพใหญ่) =====
        scale = 3
        enlarged = cv2.resize(cropped, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        
        if save_crop:
            enlarged_path = os.path.join(OUTPUT_FOLDER, save_crop.replace('.png', '_enlarged.png'))
            cv2.imwrite(enlarged_path, enlarged)
        
        # ===== ใช้ EasyOCR =====
        print(f"      ขนาดภาพ: {cropped.shape[1]}x{cropped.shape[0]} -> ขยาย: {enlarged.shape[1]}x{enlarged.shape[0]}")
        
        # อ่านจากภาพขยาย
        results = reader.readtext(enlarged, allowlist='0123456789', detail=0)
        
        if results:
            # เอาเฉพาะผลลัพธ์แรก (ไม่รวม noise จากปุ่ม+ หรืออื่นๆ)
            text = results[0]
            print(f"      EasyOCR พบ: {results} -> ใช้: '{text}'")
            return text.strip(), cropped
        
        # ถ้าไม่เจอ ลอง preprocess ก่อน
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        
        # Threshold เพื่อให้ชัด (ไม่ invert เพราะตัวเลขสีขาวบนพื้นเข้ม)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        if save_crop:
            processed_path = os.path.join(OUTPUT_FOLDER, save_crop.replace('.png', '_processed.png'))
            cv2.imwrite(processed_path, thresh)
        
        # ลองอ่านจากภาพ threshold
        results = reader.readtext(thresh, allowlist='0123456789', detail=0)
        if results:
            text = results[0]  # เอาเฉพาะตัวแรก
            print(f"      EasyOCR (threshold) พบ: {results} -> ใช้: '{text}'")
            return text.strip(), cropped
        
        # ลอง invert สี
        inverted = cv2.bitwise_not(gray)
        _, thresh_inv = cv2.threshold(inverted, 127, 255, cv2.THRESH_BINARY)
        
        if save_crop:
            inverted_path = os.path.join(OUTPUT_FOLDER, save_crop.replace('.png', '_inverted.png'))
            cv2.imwrite(inverted_path, thresh_inv)
        
        results = reader.readtext(thresh_inv, allowlist='0123456789', detail=0)
        if results:
            text = results[0]  # เอาเฉพาะตัวแรก
            print(f"      EasyOCR (inverted) พบ: {results} -> ใช้: '{text}'")
            return text.strip(), cropped
        
        # ลองไม่จำกัด allowlist
        results = reader.readtext(enlarged, detail=0)
        if results:
            # เอาเฉพาะตัวแรกแล้วกรองเอาเฉพาะตัวเลข
            first_result = results[0]
            numbers = ''.join([c for c in first_result if c.isdigit()])
            if numbers:
                print(f"      EasyOCR (all chars) พบ: {results} -> ตัวเลข: {numbers}")
                return numbers, cropped
        
        print(f"      EasyOCR ไม่พบตัวเลข :(")
        return "", cropped
    except Exception as e:
        print(f"Error OCR region: {e}")
        return None, None

def find_template(img, template_path, threshold=0.8):
    """ค้นหารูป template ในหน้าจอ"""
    try:
        # อ่าน template
        template = cv2.imread(template_path)
        if template is None:
            print(f"   ❌ ไม่พบไฟล์: {template_path}")
            return None
        
        # แปลงเป็น grayscale
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        
        # Template matching
        result = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= threshold:
            h, w = template_gray.shape
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return {
                'x': max_loc[0],
                'y': max_loc[1],
                'width': w,
                'height': h,
                'center_x': center_x,
                'center_y': center_y,
                'confidence': max_val
            }
        return None
    except Exception as e:
        print(f"Error find_template: {e}")
        return None

def main():
    print("=" * 50)
    print("  ทดสอบ OCR อ่านข้อความจากหน้าจอ Emulator")
    print("=" * 50)
    
    # 1. ค้นหา device
    print("\n[1] ค้นหา device ที่เชื่อมต่อ...")
    device = get_connected_device()
    
    if not device:
        print("❌ ไม่พบ device ที่เชื่อมต่อ!")
        print("   กรุณาเปิด MuMu Player แล้วลองใหม่")
        return
    
    print(f"✅ พบ device: {device}")
    
    # 2. จับภาพหน้าจอ
    print("\n[2] จับภาพหน้าจอ...")
    img = capture_screen(device)
    
    if img is None:
        print("❌ ไม่สามารถจับภาพหน้าจอได้!")
        return
    
    print(f"✅ จับภาพสำเร็จ! ขนาด: {img.shape[1]}x{img.shape[0]}")
    
    # บันทึกภาพหน้าจอ
    screenshot_path = os.path.join(OUTPUT_FOLDER, "screenshot_test.png")
    cv2.imwrite(screenshot_path, img)
    print(f"   บันทึกภาพ: {screenshot_path}")
    
    # 3. OCR ทั้งหน้าจอ
    print("\n[3] อ่านข้อความด้วย OCR...")
    numbers, all_text = ocr_full_screen(img)
    
    print("\n" + "=" * 50)
    print("  ผลลัพธ์ OCR")
    print("=" * 50)
    
    print("\n📌 ตัวเลขที่พบ:")
    if numbers:
        # แยกตัวเลขออกมา
        nums = [n for n in numbers.split() if n]
        for num in nums:
            print(f"   - {num}")
        print(f"\n   รวม: {len(nums)} ตัวเลข")
    else:
        print("   (ไม่พบตัวเลข)")
    
    print("\n📌 ข้อความทั้งหมด:")
    if all_text:
        # แสดงเฉพาะ 500 ตัวอักษรแรก
        if len(all_text) > 500:
            print(f"   {all_text[:500]}...")
            print(f"   (... และอีก {len(all_text) - 500} ตัวอักษร)")
        else:
            print(f"   {all_text}")
    else:
        print("   (ไม่พบข้อความ)")
    
    # 4. ค้นหา checktiket.png แล้วอ่านตัวเลข
    print("\n" + "=" * 50)
    print("  🎫 ค้นหา checktiket.png แล้วอ่านตัวเลข")
    print("=" * 50)
    
    template_path = "img/checktiket.png"
    print(f"\n📍 ค้นหารูป: {template_path}")
    
    match = find_template(img, template_path, threshold=0.7)
    
    if match:
        print(f"   ✅ พบ checktiket.png!")
        print(f"   ตำแหน่ง: ({match['x']}, {match['y']})")
        print(f"   ขนาดรูป template: {match['width']}x{match['height']}")
        print(f"   ความแม่นยำ: {match['confidence']:.2%}")
        
        # บันทึกภาพพื้นที่ที่เจอ
        x, y, w, h = match['x'], match['y'], match['width'], match['height']
        matched_area = img[y:y+h, x:x+w]
        tiket_found_path = os.path.join(OUTPUT_FOLDER, "checktiket_found.png")
        cv2.imwrite(tiket_found_path, matched_area)
        print(f"   บันทึกภาพที่เจอ: {tiket_found_path}")
        
        # อ่านตัวเลขจากพื้นที่ที่เจอ
        # จากรูป checktiket.png (116x43): ไอคอน=0-45px, ตัวเลข=80-116px
        print("\n   🔍 อ่านตัวเลขจากพื้นที่:")
        
        # ===== ตัดเฉพาะตัวเลขด้านขวาสุด (ข้ามไอคอนตั๋ว) =====
        # ตัวเลขอยู่ประมาณ 70% ขวาสุดของพื้นที่
        ocr_x = x + int(w * 0.70)  # เริ่มที่ 70% จากซ้าย (ข้ามไอคอน)
        ocr_y = y + 5              # เว้นขอบบน
        ocr_w = int(w * 0.28)      # ความกว้าง 28% (เฉพาะตัวเลข)
        ocr_h = h - 10             # ความสูง (เว้นขอบบน-ล่าง)
        
        # อ่าน OCR
        text, cropped = ocr_region(img, ocr_x, ocr_y, ocr_w, ocr_h, save_crop="ticket_number_only.png")
        
        print(f"   พื้นที่ OCR: ({ocr_x}, {ocr_y}) ขนาด {ocr_w}x{ocr_h}")
        print(f"   บันทึกภาพ: ticket_number_only.png")
        
        if text:
            print(f"\n   🎯 ตัวเลข Ticket: {text}")
        else:
            # ถ้าไม่เจอตัวเลข อาจเป็น 0
            print("\n   ⚠️ ไม่พบตัวเลข (อาจเป็น 0 หรือว่าง)")
            print("   ลองดูไฟล์ ticket_number_only.png และ ticket_number_only_processed.png")
        
        # ลองอ่านจากพื้นที่กว้างขึ้น
        print("\n   🔍 ลองอ่านจากพื้นที่กว้างขึ้น:")
        ocr_x2 = x + int(w * 0.55)  # เริ่มที่ 55%
        ocr_w2 = int(w * 0.43)       # ความกว้าง 43%
        text2, _ = ocr_region(img, ocr_x2, ocr_y, ocr_w2, ocr_h, save_crop="ticket_number_wide.png")
        print(f"   พื้นที่ OCR: ({ocr_x2}, {ocr_y}) ขนาด {ocr_w2}x{ocr_h}")
        if text2:
            print(f"   ตัวเลข: {text2}")
        else:
            print("   (ไม่พบตัวเลข)")
            
    else:
        print("   ❌ ไม่พบ checktiket.png ในหน้าจอ")
        print("   ลองลด threshold หรือตรวจสอบว่าหน้าจอเกมแสดง ticket หรือไม่")
        ticket_value = None
    
    # 5. ค้นหา checkruby.png แล้วอ่านตัวเลข
    print("\n" + "=" * 50)
    print("  💎 ค้นหา checkruby.png แล้วอ่านตัวเลข")
    print("=" * 50)
    
    ruby_template_path = "img/checkruby.png"
    print(f"\n📍 ค้นหารูป: {ruby_template_path}")
    
    ruby_match = find_template(img, ruby_template_path, threshold=0.7)
    ruby_value = None
    
    if ruby_match:
        print(f"   ✅ พบ checkruby.png!")
        print(f"   ตำแหน่ง: ({ruby_match['x']}, {ruby_match['y']})")
        print(f"   ขนาดรูป template: {ruby_match['width']}x{ruby_match['height']}")
        print(f"   ความแม่นยำ: {ruby_match['confidence']:.2%}")
        
        # บันทึกภาพพื้นที่ที่เจอ
        rx, ry, rw, rh = ruby_match['x'], ruby_match['y'], ruby_match['width'], ruby_match['height']
        ruby_matched_area = img[ry:ry+rh, rx:rx+rw]
        ruby_found_path = os.path.join(OUTPUT_FOLDER, "checkruby_found.png")
        cv2.imwrite(ruby_found_path, ruby_matched_area)
        print(f"   บันทึกภาพที่เจอ: {ruby_found_path}")
        
        # อ่านตัวเลขจากพื้นที่ที่เจอ
        # จากรูป checkruby.png: ไอคอนเพชร=0-25px, ตัวเลข=25-80px, ปุ่ม+=80-125px
        print("\n   🔍 อ่านตัวเลข Ruby:")
        
        # ตัดเฉพาะตัวเลข (ด้านขวาของไอคอนเพชร, ก่อนปุ่ม +)
        # ปรับให้กว้างขึ้นเพื่อให้ได้ตัวเลขครบ
        ruby_ocr_x = rx + int(rw * 0.22)  # เริ่มที่ 22% จากซ้าย (ข้ามไอคอนเพชร)
        ruby_ocr_y = ry + 3               # เว้นขอบบนน้อยลง
        ruby_ocr_w = int(rw * 0.50)       # ความกว้าง 50% (กว้างขึ้น ไม่รวมปุ่ม+)
        ruby_ocr_h = rh - 6               # ความสูง (เว้นขอบน้อยลง)
        
        ruby_text, _ = ocr_region(img, ruby_ocr_x, ruby_ocr_y, ruby_ocr_w, ruby_ocr_h, save_crop="ruby_number_only.png")
        
        print(f"   พื้นที่ OCR: ({ruby_ocr_x}, {ruby_ocr_y}) ขนาด {ruby_ocr_w}x{ruby_ocr_h}")
        print(f"   บันทึกภาพ: ruby_number_only.png")
        
        if ruby_text:
            print(f"\n   🎯 ตัวเลข Ruby: {ruby_text}")
            ruby_value = ruby_text
        else:
            # ลองพื้นที่กว้างขึ้นอีก
            print("\n   🔍 ลองพื้นที่กว้างขึ้น:")
            ruby_ocr_x2 = rx + int(rw * 0.18)
            ruby_ocr_w2 = int(rw * 0.55)  # กว้างขึ้นอีก
            ruby_text2, _ = ocr_region(img, ruby_ocr_x2, ruby_ocr_y, ruby_ocr_w2, ruby_ocr_h, save_crop="ruby_number_wide.png")
            if ruby_text2:
                print(f"   🎯 ตัวเลข Ruby: {ruby_text2}")
                ruby_value = ruby_text2
            else:
                print("   ⚠️ ไม่พบตัวเลข")
    else:
        print("   ❌ ไม่พบ checkruby.png ในหน้าจอ")
    
    # 6. สรุปผล
    print("\n" + "=" * 50)
    print("  📊 สรุปผล")
    print("=" * 50)
    
    # ดึงค่า ticket จากก่อนหน้า
    if 'text' in dir() and text:
        ticket_value = text
    elif 'text2' in dir() and text2:
        ticket_value = text2
    else:
        ticket_value = None
    
    print(f"\n   🎫 ตัวเลข Ticket: {ticket_value if ticket_value else '(ไม่พบ)'}")
    print(f"   💎 เพชร Ruby: {ruby_value if ruby_value else '(ไม่พบ)'}")
    
    print("\n" + "=" * 50)
    print("  เสร็จสิ้นการทดสอบ!")
    print("=" * 50)

if __name__ == "__main__":
    main()
