import cv2
import numpy as np
import easyocr
import subprocess
import os

# --- CONFIGURATION ---
DEVICE_ID = "emulator-5556"

if os.path.exists(r"adb\adb.exe"):
    ADB_PATH = os.path.abspath(r"adb\adb.exe")
else:
    ADB_PATH = "adb"

# Target regions (x, y, w, h)
REGIONS = {
    "RUBY":   {"x": 427, "y": 20, "w": 51, "h": 16},
    "TICKET": {"x": 558, "y": 20, "w": 56, "h": 16}
}

# Best preprocessing variant per region
BEST_VARIANT = {
    "RUBY":   "manual_180",
    "TICKET": "manual_180"
}

# --- ADB HELPER ---

def adb_capture(device_id, save_path):
    print(f"[ADB] Capturing screen for {device_id}...")
    temp_remote = "/sdcard/screen_temp.png"
    try:
        subprocess.run([ADB_PATH, "-s", device_id, "shell", "screencap", "-p", temp_remote], check=True, shell=True)
        subprocess.run([ADB_PATH, "-s", device_id, "pull", temp_remote, save_path], check=True, shell=True)
        print(f"[ADB] Screenshot saved to: {save_path}")
    except Exception as e:
        print(f"[ADB ERROR] {e}")
        raise

# --- PREPROCESSING ---

def preprocess(gray, variant, scale):
    upscaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    if variant == "otsu_inv":
        _, result = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    elif variant == "otsu_norm":
        _, result = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    elif variant == "clahe_otsu_inv":
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(upscaled)
        _, result = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    elif variant == "adaptive":
        blur = cv2.GaussianBlur(upscaled, (3, 3), 0)
        result = cv2.adaptiveThreshold(blur, 255,
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 15, 4)

    elif variant == "manual_180":
        _, result = cv2.threshold(upscaled, 180, 255, cv2.THRESH_BINARY_INV)

    elif variant == "sharpen_otsu_inv":
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(upscaled, -1, kernel)
        _, result = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    else:
        raise ValueError(f"Unknown variant: {variant}")

    return result

# --- OCR ---

def read_region(reader, full_img, label, r):
    img_h, img_w = full_img.shape[:2]

    # ปรับ padding สำหรับ Ruby ให้แคบลงเพื่อลดนอยส์
    PAD = 2 if label == "RUBY" else 10
    x1 = max(0, r['x'] - PAD)
    y1 = max(0, r['y'] - PAD)
    x2 = min(img_w, r['x'] + r['w'] + PAD)
    y2 = min(img_h, r['y'] + r['h'] + PAD)

    cropped = full_img[y1:y2, x1:x2]
    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)

    # Scale: region เล็ก (สูง < 30px) ใช้ 6x, อื่นๆ ใช้ 3x
    scale = 6 if r['h'] < 30 else 3
    variant = BEST_VARIANT[label]
    processed = preprocess(gray, variant, scale)

    results = reader.readtext(
        processed,
        allowlist='0123456789,',
        detail=0,
        width_ths=0.3,
        min_size=10,
        text_threshold=0.3,
        low_text=0.2,
    )
    combined = "".join(results)
    final_text = "".join([c for c in combined if c.isdigit()])

    print(f"[{label}] variant={variant} raw={results} -> '{final_text}'")
    return final_text if final_text else None

# --- MAIN ---

def main():
    print("Initializing...")
    debug_dir = "test_debug_strict"
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
    os.chdir(debug_dir)

    global ADB_PATH
    if not os.path.isabs(ADB_PATH) and os.path.exists(os.path.join("..", ADB_PATH)):
        ADB_PATH = os.path.abspath(os.path.join("..", ADB_PATH))

    print("Loading EasyOCR Reader...")
    reader = easyocr.Reader(['en'], gpu=False)

    try:
        screenshot_path = "raw_screenshot.png"
        adb_capture(DEVICE_ID, screenshot_path)

        full_img = cv2.imread(screenshot_path)
        if full_img is None:
            print("Error: Could not read screenshot.")
            return

        # วาด debug boxes
        debug_box_img = full_img.copy()
        for lbl, r in REGIONS.items():
            cv2.rectangle(debug_box_img,
                          (r['x'], r['y']),
                          (r['x'] + r['w'], r['y'] + r['h']),
                          (0, 0, 255), 2)
            cv2.putText(debug_box_img, lbl,
                        (r['x'], r['y'] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.imwrite("raw_screenshot_with_boxes.png", debug_box_img)

        # อ่านค่าทุก region
        results = {}
        for lbl, r in REGIONS.items():
            results[lbl] = read_region(reader, full_img, lbl, r)

        print("\n========== SUMMARY ==========")
        for lbl, val in results.items():
            print(f"  {lbl}: {val if val else 'NOT FOUND'}")

    except Exception as e:
        print(f"Runtime Error: {e}")

if __name__ == "__main__":
    main()