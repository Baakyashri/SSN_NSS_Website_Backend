import os

# Simulate the path calculation from album.py
current_file = __file__
print(f"Current file: {current_file}")

# Get the directory of the current file (nss-backend)
backend_dir = os.path.dirname(current_file)
print(f"Backend dir: {backend_dir}")

# Go up two levels to get to the project root
project_root = os.path.dirname(os.path.dirname(backend_dir))
print(f"Project root: {project_root}")

# Assets path
assets_path = os.path.join(project_root, 'assets')
print(f"Assets path: {assets_path}")

# Check if assets directory exists
print(f"Assets directory exists: {os.path.exists(assets_path)}")

# List contents of assets
if os.path.exists(assets_path):
    print("Assets contents:")
    for item in os.listdir(assets_path):
        print(f"  {item}")
else:
    print("Assets directory not found")

# Test a specific file
test_file = 'nss-logo.png'
test_path = os.path.join(assets_path, test_file)
print(f"Test file path: {test_path}")
print(f"Test file exists: {os.path.exists(test_path)}")
