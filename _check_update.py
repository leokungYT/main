"""Popup ถามผู้ใช้ว่าจะอัพเดทหรือไม่ - ถูกเรียกจาก loginสะสม.bat"""
import tkinter as tk
from tkinter import messagebox
import sys

root = tk.Tk()
root.attributes('-topmost', True)
root.withdraw()

res = messagebox.askyesno(
    'แจ้งเตือนอัพเดทใหม่!',
    'พบโค้ดเวอร์ชั่นใหม่ล่าสุดอยู่บน Github\n'
    'คุณต้องการอัพเดทโปรแกรมในเครื่องนี้ให้เป็นอันใหม่เลยหรือไม่?\n\n'
    '[ Yes ] = บังคับอัพเดทดึงไฟล์ใหม่มาทับให้หมด\n'
    '[ No ] = ไม่สนใจการอัพเดท รันโปรแกรมด้วยเวอร์ชั่นเดิม'
)

root.destroy()
sys.exit(0 if res else 1)
