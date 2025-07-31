#!/usr/bin/env python3

import subprocess
import pathlib
import sys
import datetime

# Test just one single experiment
def test_single_experiment():
    print("🧪 Testing single experiment...")
    sys.stdout.flush()
    
    # Paths
    lacam_script = "lacam.py"
    exe_path = "build/main"
    map_file = "scripts/map/ost003d.map"
    scenario_file = "scripts/scen/ost003d/ost003d-random-1.scen"
    output_dir = "test_single_output"
    
    # Check files exist
    print("📁 Checking files:")
    for path_name, path in [("lacam.py", lacam_script), ("executable", exe_path), 
                           ("map", map_file), ("scenario", scenario_file)]:
        exists = pathlib.Path(path).exists()
        print(f"   {path_name}: {path} -> {exists}")
    sys.stdout.flush()
    
    # Command
    cmd = [
        "python3", lacam_script,
        "--exe", exe_path,
        "--map", map_file,
        "--scen", scenario_file,
        "--num", "50",  # Smaller number for faster test
        "--timeout", "30",  # Shorter timeout for test
        "--out", output_dir
    ]
    
    print(f"🔧 Command: {' '.join(cmd)}")
    print(f"⏰ Starting at {datetime.datetime.now()}")
    sys.stdout.flush()
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print(f"⏰ Completed at {datetime.datetime.now()}")
        print(f"📊 Return code: {result.returncode}")
        
        if result.stdout:
            print(f"📤 Stdout:\n{result.stdout}")
        if result.stderr:
            print(f"📥 Stderr:\n{result.stderr}")
            
        # Check if output directory was created
        output_path = pathlib.Path(output_dir)
        print(f"📂 Output directory exists: {output_path.exists()}")
        if output_path.exists():
            files = list(output_path.glob("*"))
            print(f"📄 Output files: {[f.name for f in files]}")
            
    except subprocess.TimeoutExpired:
        print("❌ Test timed out!")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    sys.stdout.flush()

if __name__ == "__main__":
    test_single_experiment() 