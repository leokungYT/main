import cv2
import numpy as np
import easyocr
import subprocess
import os
import time

# --- CONFIGURATION (Common ADB paths) ---
DEVICE_ID = "emulator-5556" 

# Secure the absolute path before any directory changes
if os.path.exists(r"adb\adb.exe"):
    ADB_PATH = os.path.abspath(r"adb\adb.exe")
else:
    ADB_PATH = "adb" # Fallback to system path

# Target regions (x, y, w, h)
REGIONS = {
    "RUBY":   {"x": 428, "y": 20, "w": 52, "h": 16},
    "TICKET": {"x": 558, "y": 20, "w": 56, "h": 16}
}

# --- SYSTEM HELPERS ---

def adb_capture(device_id, save_path):
    """Pull screenshot from device via ADB"""
    print(f"[ADB] Capturing screen for {device_id}...")
    temp_remote = "/sdcard/screen_temp.png"
    subprocess.run([ADB_PATH, "-s", device_id, "shell", "screencap", "-p", temp_remote], check=True, shell=True)
    subprocess.run([ADB_PATH, "-s", device_id, "pull", temp_remote, save_path], check=True, shell=True)
    print(f"[ADB] Screenshot saved to: {save_path}")

def clean_ocr_text(text_list):
    """Clean and combine OCR text into numeric-friendly format"""
    mapper = {
        'O': '0', 'o': '0', 'D': '0', 'Q': '0', '()': '0', '@': '0',
        'I': '1', 'l': '1', 'i': '1', '|': '1', '!': '1',
        'Z': '2', 'z': '2', '7': '7', 'T': '7',
        'S': '5', 's': '5', '$': '5',
        'B': '8', 'E': '8', 'g': '9', 'q': '9'
    }
    
    combined = "".join(text_list)
    found_digits = ""
    for char in combined:
        if char.isdigit():
            found_digits += char
        elif char in mapper:
            found_digits += mapper[char]
            
    # Fallback to zero if circular text detected
    if not found_digits and any(c in "OoDQ()@U" for c in combined):
        return "0 (Mapped from text)"
        
    return found_digits if found_digits else "Empty"

# --- MAIN OCR TEST ---

def test_region_ocr(reader, full_img, label, r):
    print(f"\n===== TESTING {label} (STRICT) =====")
    
    # 1. Crop
    cropped = full_img[r['y']:r['y']+r['h'], r['x']:r['x']+r['w']]
    cv2.imwrite(f"crop_{label}_original.png", cropped)
    
    # 2. Pre-processing Styles (Strict Focus)
    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    v_norm = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    v_norm = cv2.resize(v_norm, None, fx=2, fy=1.5, interpolation=cv2.INTER_CUBIC)
    
    # Mode: Strict Binary
    _, v_bin = cv2.threshold(v_norm, 160, 255, cv2.THRESH_BINARY_INV)
    cv2.imwrite(f"debug_{label}_STRICT.png", v_bin)
    
    # 3. Run OCR (Digits Only)
    results = reader.readtext(v_bin, allowlist='0123456789', detail=0)
    print(f"[STRICT] Result: {results} -> Final: {''.join(results)}")

def main():
    print("Initializing test environment...")
    debug_dir = f"test_debug_strict"
    if not os.path.exists(debug_dir): os.makedirs(debug_dir)
    os.chdir(debug_dir)
    
    print("Loading EasyOCR Reader...")
    reader = easyocr.Reader(['en'], gpu=False)
    
    try:
        # Capture screen
        screenshot_path = "raw_screenshot.png"
        adb_capture(DEVICE_ID, screenshot_path)
        
        full_img = cv2.imread(screenshot_path)
        if full_img is None:
            print("Error: Could not read screenshot image.")
            return

        # Run tests
        for label, r in REGIONS.items():
            test_region_ocr(reader, full_img, label, r)
            
        print("\nTest procedure completed.")
        print(f"Check the folder '{debug_dir}' for results and images.")
        
    except Exception as e:
        print(f"Runtime Error: {e}")

if __name__ == "__main__":
    main()
