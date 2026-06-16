import os
from config import UPLOAD_FOLDER

filename = "677695c3-def6-4162-9d5a-9cbd0a2370d0_IMG_20250920_091555584.jpg"
file_path = os.path.join(UPLOAD_FOLDER, filename)

print(f"UPLOAD_FOLDER: {UPLOAD_FOLDER}")
print(f"File path: {file_path}")
print(f"File exists: {os.path.exists(file_path)}")
print(f"Absolute file path: {os.path.abspath(file_path)}")
