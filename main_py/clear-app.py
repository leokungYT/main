from ppadb.client import Client as AdbClient
import subprocess
import time
import os
from colorama import Fore, Style
import colorama

colorama.init(autoreset=True)

# ⭐ AUTO SCAN CONFIGURATION
START_PORT = 5557
MAX_DEVICES = 30
MUMU_PORTS = [START_PORT + (i * 2) for i in range(MAX_DEVICES)]

def start_adb_server():
    try:
        subprocess.run(["adb", "kill-server"], capture_output=True, timeout=3)
        time.sleep(0.1)
        subprocess.run(["adb", "start-server"], capture_output=True, timeout=3)
        time.sleep(0.5)
        print(f"{Fore.GREEN}[INFO] ADB server started{Style.RESET_ALL}")
        return True
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to start ADB: {str(e)}{Style.RESET_ALL}")
        return False

def connect_to_devices():
    try:
        adb = AdbClient(host="127.0.0.1", port=5037)
        
        # ตรวจสอบ devices ที่เชื่อมต่ออยู่
        existing_devices = adb.devices()
        if existing_devices:
            print(f"{Fore.GREEN}[INFO] Found {len(existing_devices)} device(s) connected{Style.RESET_ALL}")
            for device in existing_devices:
                print(f"{Fore.GREEN}  ✓ {device.serial}{Style.RESET_ALL}")
            return existing_devices
        
        # Auto-scan ports
        print(f"{Fore.CYAN}[INFO] Scanning ports from {START_PORT}...{Style.RESET_ALL}")
        connected_devices = []
        
        for port in MUMU_PORTS:
            try:
                result = subprocess.run(
                    ["adb", "connect", f"127.0.0.1:{port}"],
                    capture_output=True,
                    timeout=2,
                    text=True
                )
                time.sleep(0.3)
                
                if "connected" in result.stdout.lower():
                    devices = adb.devices()
                    for device in devices:
                        if f":{port}" in device.serial and device not in connected_devices:
                            print(f"{Fore.GREEN}  ✓ Connected: {device.serial}{Style.RESET_ALL}")
                            connected_devices.append(device)
                            break
            except:
                continue
        
        if connected_devices:
            print(f"\n{Fore.GREEN}[SUCCESS] Total {len(connected_devices)} device(s) connected{Style.RESET_ALL}")
            return connected_devices
        
        print(f"{Fore.RED}[ERROR] No devices found{Style.RESET_ALL}")
        return []
        
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Connection failed: {str(e)}{Style.RESET_ALL}")
        return []

def clear_app(device):
    try:
        print(f"{Fore.YELLOW}[DEVICE {device.serial}] Clearing app...{Style.RESET_ALL}")
        device.shell("am force-stop com.linecorp.LGRGS")
        time.sleep(0.5)
        print(f"{Fore.GREEN}[DEVICE {device.serial}] App cleared successfully{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[DEVICE {device.serial}] Error: {str(e)}{Style.RESET_ALL}")

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}LINE RANGER - CLEAR APP TOOL{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}\n")
    
    if not start_adb_server():
        input("\nPress Enter to exit...")
        return
    
    devices = connect_to_devices()
    
    if not devices:
        print(f"\n{Fore.RED}No devices found. Please start MuMu Player first.{Style.RESET_ALL}")
        input("\nPress Enter to exit...")
        return
    
    print(f"\n{Fore.YELLOW}Clearing app on all devices...{Style.RESET_ALL}\n")
    
    for device in devices:
        clear_app(device)
    
    print(f"\n{Fore.GREEN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}All devices cleared successfully!{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'='*50}{Style.RESET_ALL}")
    
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    try:
        main()
    finally:
        colorama.deinit()