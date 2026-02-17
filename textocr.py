import pytesseract
import cv2
import ranger as rg

class Location:
    def __init__(self, x: int, y: int):
        self.x = int(x)
        self.y = int(y)

    def getX(self) -> float:
        return float(self.x)

    def getY(self) -> float:
        return float(self.y)

    def setLocation(self, x: int, y: int):
        self.x = int(x)
        self.y = int(y)

    def offset(self, dx: int, dy: int):
        return Location(self.x + dx, self.y + dy)

    def above(self, dy: int):
        return Location(self.x, self.y - dy)

    def below(self, dy: int):
        return Location(self.x, self.y + dy)

    def left(self, dx: int):
        return Location(self.x - dx, self.y)

    def right(self, dx: int):
        return Location(self.x + dx, self.y)

    def __repr__(self):
        return f"Location(x={self.x}, y={self.y})"
    


class Region:
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    # ---- Getters ----
    def getX(self): return self.x
    def getY(self): return self.y
    def getW(self): return self.w
    def getH(self): return self.h

    def getTopLeft(self): return Location(self.x, self.y)
    def getTopRight(self): return Location(self.x + self.w, self.y)
    def getBottomLeft(self): return Location(self.x, self.y + self.h)
    def getBottomRight(self): return Location(self.x + self.w, self.y + self.h)
    def getCenter(self): return Location(self.x + self.w // 2, self.y + self.h // 2)
    def getTopCenter(self): return Location(self.x + self.w // 2, self.y)
    def getBottomCenter(self): return Location(self.x + self.w // 2, self.y + self.h)
    def getLeftCenter(self): return Location(self.x, self.y + self.h // 2)
    def getRightCenter(self): return Location(self.x + self.w, self.y + self.h // 2)

    # ---- Setters ----
    def setX(self, number: int): self.x = int(number)
    def setY(self, number: int): self.y = int(number)
    def setW(self, number: int): self.w = int(number)
    def setH(self, number: int): self.h = int(number)

    def __repr__(self):
        return f"Region(x={self.x}, y={self.y}, w={self.w}, h={self.h})"




def numberOCR(region:Region,  psm=7, imageProcessing=True):
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    # อ่านภาพภายใน region (BGR)
    rg.capture_screen()
    img = cv2.imread(rg.filename)[region.y:region.y+region.h, region.x:region.x+region.w]

    # -----------------------------
    # 1. แปลงภาพ + ทำ Threshold
    # -----------------------------
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if imageProcessing:
        gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_LINEAR)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        thresh = gray

    # -----------------------------
    # Debug (ดูผลการ crop) debug img
    # # -----------------------------
    # cv2.imshow("thresh", thresh)
    # cv2.waitKey()

    # -----------------------------
    # 4. OCR ด้วย Tesseract
    # -----------------------------
    config = (
        f"--psm {psm} "
        "-c tessedit_char_whitelist=0123456789' "
        "-c load_system_dawg=0 -c load_freq_dawg=0 "
    )

    text = pytesseract.image_to_string(thresh, lang="eng", config=config)
    return text.strip()




def textOCR(region:Region,  psm=7, imageProcessing=True):
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    # อ่านภาพภายใน region (BGR)
    rg.capture_screen()
    img = cv2.imread(rg.filename)[region.y:region.y+region.h, region.x:region.x+region.w]

    # -----------------------------
    # 1. แปลงภาพ + ทำ Threshold
    # -----------------------------
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if imageProcessing:
        gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_LINEAR)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        thresh = gray

    # -----------------------------
    # Debug (ดูผลการ crop) debug img
    # # -----------------------------
    # cv2.imshow("thresh", thresh)
    # cv2.waitKey()

    # -----------------------------
    # 4. OCR ด้วย Tesseract
    # -----------------------------
    config = (
        f"--psm {psm} "
        "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789[]' "
        "-c load_system_dawg=0 -c load_freq_dawg=0 "
    )

    text = pytesseract.image_to_string(thresh, lang="eng", config=config)
    return text.strip()
