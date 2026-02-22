@echo off
title Ranger+Gear Dependency Installer
echo ====================================================
echo  Ranger+Gear Dependency Installer
echo ====================================================
echo.
echo [1/6] Installing OpenCV...
pip install opencv-python

echo.
echo [2/6] Installing NumPy...
pip install numpy

echo.
echo [3/6] Installing Colorama...
pip install colorama

echo.
echo [4/6] Installing Pillow (Image processing)...
pip install Pillow

echo.
echo [5/6] Installing CustomTkinter (Modern GUI)...
pip install customtkinter

echo.
echo [6/6] Installing EasyOCR...
pip install easyocr

echo.
echo ====================================================
echo  Installation Complete!
echo ====================================================
echo.
pause
