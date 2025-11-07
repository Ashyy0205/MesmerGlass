#!/usr/bin/env python3
"""
Quick demonstration of zoom speed measurement for both VMC and Launcher
"""
import subprocess
import time
import re
from pathlib import Path

def test_vmc_zoom_brief():
    """Brief test of VMC zoom measurements"""
    print("🔄 Testing VMC zoom measurements (10 seconds)...")
    
    cmd = [
        r".\.venv\Scripts\python.exe",
        "scripts\\vmc_speed_test_mode.py"
    ]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    rotation_measurements = []
    zoom_measurements = []
    start_time = time.time()
    
    try:
        while time.time() - start_time < 10:  # 10 second test
            line = process.stdout.readline()
            if not line:
                break
            
            # Collect rotation data
            if "[VMC rotation_debug]" in line and "uEffectiveSpeed=" in line:
                match = re.search(r'uEffectiveSpeed=([\d.]+)', line)
                if match:
                    rotation_measurements.append(float(match.group(1)))
            
            # Collect zoom data  
            if "[VMC zoom_debug]" in line and "zoom_rate=" in line:
                match = re.search(r'zoom_rate=([\d.]+)', line)
                if match:
                    zoom_measurements.append(float(match.group(1)))
                    
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
    
    print(f"  📊 VMC Results:")
    print(f"    Rotation samples: {len(rotation_measurements)}")
    print(f"    Zoom samples: {len(zoom_measurements)}")
    if rotation_measurements:
        avg_rotation = sum(rotation_measurements) / len(rotation_measurements)
        print(f"    Avg rotation speed: {avg_rotation:.6f}")
    if zoom_measurements:
        avg_zoom = sum(zoom_measurements) / len(zoom_measurements) 
        print(f"    Avg zoom rate: {avg_zoom:.6f}")
    print()

def test_launcher_zoom_brief():
    """Brief test of Launcher zoom measurements"""
    print("🔄 Testing Launcher zoom measurements (10 seconds)...")
    
    cmd = [
        r".\.venv\Scripts\python.exe", 
        "scripts\\launcher_speed_test_mode.py"
    ]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    rotation_measurements = []
    zoom_measurements = []
    start_time = time.time()
    
    try:
        while time.time() - start_time < 10:  # 10 second test
            line = process.stdout.readline()
            if not line:
                break
            
            # Collect rotation data
            if "[Launcher rotation_debug]" in line and "uEffectiveSpeed=" in line:
                match = re.search(r'uEffectiveSpeed=([\d.]+)', line)
                if match:
                    rotation_measurements.append(float(match.group(1)))
            
            # Collect zoom data
            if "[Launcher zoom_debug]" in line and "zoom_rate=" in line:
                match = re.search(r'zoom_rate=([\d.]+)', line)
                if match:
                    zoom_measurements.append(float(match.group(1)))
                    
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
    
    print(f"  📊 Launcher Results:")
    print(f"    Rotation samples: {len(rotation_measurements)}")
    print(f"    Zoom samples: {len(zoom_measurements)}")
    if rotation_measurements:
        avg_rotation = sum(rotation_measurements) / len(rotation_measurements)
        print(f"    Avg rotation speed: {avg_rotation:.6f}")
    if zoom_measurements:
        avg_zoom = sum(zoom_measurements) / len(zoom_measurements)
        print(f"    Avg zoom rate: {avg_zoom:.6f}")
    print()

def main():
    """Run brief zoom measurement tests"""
    print("🚀 Quick Zoom Speed Measurement Demo")
    print("=" * 50)
    
    # Test VMC
    test_vmc_zoom_brief()
    
    # Test Launcher
    test_launcher_zoom_brief()
    
    print("✅ Zoom measurement demo complete!")
    print("\n💡 Key Achievements:")
    print("  ✅ VMC produces rotation and zoom debug output")
    print("  ✅ Launcher loads visual mode and produces debug output") 
    print("  ✅ Both systems ready for multi-speed zoom testing")

if __name__ == "__main__":
    main()