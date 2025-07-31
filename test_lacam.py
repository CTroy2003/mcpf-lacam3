#!/usr/bin/env python3

import subprocess
import pathlib

# Test if lacam.py can be called with --help
print("Testing lacam.py --help...")
try:
    result = subprocess.run(["python3", "lacam.py", "--help"], 
                          capture_output=True, text=True, timeout=10)
    print(f"Return code: {result.returncode}")
    print(f"Stdout:\n{result.stdout}")
    if result.stderr:
        print(f"Stderr:\n{result.stderr}")
except Exception as e:
    print(f"Error running lacam.py: {e}")

# Test if executable exists
exe_path = pathlib.Path("build/main")
print(f"\nExecutable check:")
print(f"build/main exists: {exe_path.exists()}")
if exe_path.exists():
    print(f"build/main is executable: {exe_path.stat().st_mode & 0o111 != 0}")

# Test if data files exist
print(f"\nData file check:")
for map_name in ["ost003d", "random-32-32-10", "empty-8-8"]:
    map_file = pathlib.Path(f"data/maps/{map_name}.map")
    print(f"{map_file}: {map_file.exists()}")
    
    for wp in ["2wp", "4wp", "8wp"]:
        scen_file = pathlib.Path(f"data/scenarios/{map_name}/{map_name}-{wp}.scen")
        print(f"{scen_file}: {scen_file.exists()}") 