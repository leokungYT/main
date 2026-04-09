import os
import cv2
import numpy as np
import subprocess
import time

def get_adb_path():
    mumu_adb_paths = [
        "F:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
        "F:\\Program Files\\Netease\\MuMuPlayer\\nx_main\\adb.exe",
        "C:\\Program Files\\Netease\\MuMuPlayerGlobal-12.0\\shell\\adb.exe",
        "C:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
        "F:\\MuMuPlayerGlobal-12.0\\shell\\adb.exe",
        "D:\\MuMuPlayerGlobal-12.0\\shell\\adb.exe",
        "E:\\MuMuPlayerGlobal-12.0\\shell\\adb.exe",
        "D:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe",
        "E:\\Program Files\\Netease\\MuMuPlayer\\shell\\adb.exe"
    ]
    for path in mumu_adb_paths:
        if os.path.exists(path):
            return f'"{path}"'
    return "adb"

ADB_CMD = get_adb_path()

def ImgSearchADB(adb_img, find_img_path, threshold=0.95, method=cv2.TM_CCOEFF_NORMED):
    try:
        find_img = cv2.imread(find_img_path, cv2.IMREAD_COLOR)
        if find_img is None:
            print(f"ไม่สามารถโหลดรูปภาพ {find_img_path}")
            return [], 0
        
        needle_h, needle_w = find_img.shape[:2]
        result = cv2.matchTemplate(adb_img, find_img, method)
        
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        print(f"   -> Max Similarity: {max_val:.4f} at {max_loc}")
        
        locations = np.where(result >= threshold)
        locations = list(zip(*locations[::-1]))
        rectangles = []
        for loc in locations:
            rect = [int(loc[0]), int(loc[1]), needle_w, needle_h]
            rectangles.append(rect)
            rectangles.append(rect)
        rectangles, _ = cv2.groupRectangles(rectangles, groupThreshold=1, eps=1)
        points = []
        if len(rectangles):
            for (x, y, w, h) in rectangles:
                center_x = x + int(w / 2)
                center_y = y + int(h / 2)
                points.append((center_x, center_y))
        return points, max_val
    except Exception as e:
        print(f"Error searching image: {e}")
        return [], 0

def capture_screen(device="emulator-5556"):
    try:
        process = subprocess.Popen(
            f"{ADB_CMD} -s {device} exec-out screencap -p",
            stdout=subprocess.PIPE,
            shell=True
        )
        output, _ = process.communicate()
        image = np.frombuffer(output, dtype=np.uint8)
        return cv2.imdecode(image, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"Error capturing screen: {e}")
        return None

if __name__ == "__main__":
    device = "emulator-5556"
    print(f"Extracting screen from {device}...")
    adb_img = capture_screen(device)
    if adb_img is None:
        print("Failed to capture screen.")
        exit(1)
        
    cv2.imwrite("debug_screencap1.png", adb_img)
    print("Saved screen to debug_screencap1.png")
        
    gachaslot_path = 'img/gachaslot.png'
    print(f"\nSearching for target: {gachaslot_path}")
    
    if not os.path.exists(gachaslot_path):
        print(f"File {gachaslot_path} not found!")
        exit(1)
    
    thresholds_to_test = [0.95, 0.90, 0.85, 0.80, 0.70]
    
    found = False
    for thresh in thresholds_to_test:
        print(f"\n--- Testing Threshold: {thresh} ---")
        points, max_val = ImgSearchADB(adb_img, gachaslot_path, thresh)
        if points:
            print(f"✓ Found {len(points)} locations at threshold {thresh}: {points}")
            
            debug_img = adb_img.copy()
            template = cv2.imread(gachaslot_path)
            h, w = template.shape[:2]
            for cx, cy in points:
                top_left = (cx - w//2, cy - h//2)
                bottom_right = (cx + w//2, cy + h//2)
                cv2.rectangle(debug_img, top_left, bottom_right, (0, 0, 255), 3)
            cv2.imwrite("debug_result.png", debug_img)
            print(">> Saved matched image to debug_result.png")
            
            # Click the first finding!
            tx, ty = points[0]
            print(f">> Tapping location ({tx}, {ty}) immediately!")
            subprocess.run(f"{ADB_CMD} -s {device} shell input tap {tx} {ty}", shell=True)
            found = True
            break
        else:
            print(f"✗ Not found at {thresh}")
            
    if found:
        print("\n>> เจอรูปเป้าหมายและกดไปแล้ว ยุติการทดสอบ (ไม่ต้องเลื่อนหน้าจอ)")
        exit(0)
            
    print("\n--- Testing Swipe System ---")
    
    max_swipes = 5
    swipe_count = 0
    found_after_swipe = False
    
    while swipe_count < max_swipes:
        print(f"\nSimulating swipe #{swipe_count + 1} ({ADB_CMD} -s {device} shell input swipe 824 240 808 109 1000)...")
        subprocess.run(f"{ADB_CMD} -s {device} shell input swipe 824 240 808 109 1000", shell=True)
        time.sleep(2)
        
        adb_img2 = capture_screen(device)
        if adb_img2 is not None:
            cv2.imwrite(f"debug_screencap_swipe{swipe_count + 1}.png", adb_img2)
            
            points, max_val = ImgSearchADB(adb_img2, gachaslot_path, 0.85)
            if points:
                tx, ty = points[0]
                print(f"✓ Found {len(points)} locations after swipe #{swipe_count + 1}! At: {points}")
                print(f">> Tapping location ({tx}, {ty}) immediately!")
                subprocess.run(f"{ADB_CMD} -s {device} shell input tap {tx} {ty}", shell=True)
                found_after_swipe = True
                break
            else:
                print(f"✗ Still not found after swipe #{swipe_count + 1} at 0.85")
        else:
            print(f"Failed to extract screen after swipe #{swipe_count + 1}")
            
        swipe_count += 1
        
    if found_after_swipe:
        print("\n>> เจอรูปเป้าหมายหลังเลื่อนหน้าจอและกดไปแล้ว ยุติการทำงาน")
    else:
        print(f"\n>> ค้นหาไม่เจอเลยแม้จะเลื่อนหน้าจอไปแล้ว {max_swipes} ครั้ง")
