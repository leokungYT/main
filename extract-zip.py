"""Extract ZIP files from zip-input folder to backup folder (XML only)"""
import os
import zipfile
import glob

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

zip_dir = "zip-input"
backup_dir = "backup"

# Create folders
os.makedirs(zip_dir, exist_ok=True)
os.makedirs(backup_dir, exist_ok=True)

# Find ZIP files
zip_files = glob.glob(os.path.join(zip_dir, "*.zip"))

if not zip_files:
    print(f"\n[!] No ZIP files found in '{zip_dir}' folder!")
    print(f"    Please put your .zip files in the '{zip_dir}' folder")
    print(f"    then run this script again.\n")
    input("Press Enter to exit...")
    exit()

print(f"\n[OK] Found {len(zip_files)} ZIP file(s) in {zip_dir}")
print()

total_xml = 0

for zf in zip_files:
    name = os.path.basename(zf)
    print(f"[EXTRACT] {name} ...")
    
    count = 0
    try:
        with zipfile.ZipFile(zf, 'r') as z:
            for item in z.namelist():
                if item.lower().endswith('.xml'):
                    # Extract just the file (not folder structure)
                    filename = os.path.basename(item)
                    if filename:  # skip if it's a directory entry
                        data = z.read(item)
                        dst = os.path.join(backup_dir, filename)
                        with open(dst, 'wb') as f:
                            f.write(data)
                        count += 1
                        total_xml += 1
    except Exception as e:
        print(f"  [ERROR] {e}")
    
    print(f"         -> Moved {count} XML file(s) to {backup_dir}")

print(f"\n============================================")
print(f"  Done! Processed {len(zip_files)} ZIP file(s)")
print(f"  Total XML files moved to backup: {total_xml}")
print(f"============================================\n")
input("Press Enter to exit...")
