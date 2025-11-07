#!/usr/bin/env python3
"""
Quick Speed Test - 10 second version for rapid testing
"""

import time
import math
import statistics
import sys
from pathlib import Path
import subprocess
import threading

# Add MesmerGlass to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_vmc_speed(duration=15):
    """Quick VMC speed test"""
    print(f"🎯 Testing VMC for {duration}s...")
    
    vmc_script = Path(__file__).parent / "visual_mode_creator.py"
    venv_python = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
    
    process = subprocess.Popen(
        [str(venv_python), str(vmc_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    measurements = []
    start_time = time.time()
    
    def monitor():
        spiral_phase = 0.0
        rotation_speed = 4.0
        measurement_count = 0
        
        try:
            while time.time() - start_time < duration:
                line = process.stdout.readline()
                if not line:
                    break
                    
                if "[VMC rotation_debug]" in line and "time=" in line:
                    try:
                        time_val = float(line.split("time=")[1].strip())
                        spiral_phase = abs(time_val) % 1.0
                        measurements.append((time.time(), spiral_phase, rotation_speed))
                        measurement_count += 1
                        if measurement_count <= 5:  # Show first few measurements
                            print(f"  📊 VMC sample {measurement_count}: phase={spiral_phase:.6f}, speed={rotation_speed}")
                    except Exception as e:
                        print(f"  ❌ Parse error: {e} in line: {line}")
                elif "[VMC rotation_debug]" in line and "rotation_speed=" in line:
                    try:
                        rotation_speed = float(line.split("rotation_speed=")[1].strip())
                    except:
                        pass
        except:
            pass
    
    monitor_thread = threading.Thread(target=monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    time.sleep(duration)
    
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    
    print(f"  📈 VMC collected {len(measurements)} measurements")
    
    if len(measurements) < 2:
        print("❌ Not enough measurements")
        return None
    
    # Calculate speed
    phase_changes = []
    for i in range(1, len(measurements)):
        curr_time, curr_phase, _ = measurements[i]
        prev_time, prev_phase, _ = measurements[i-1]
        
        dt = curr_time - prev_time
        if dt > 0:
            phase_delta = curr_phase - prev_phase
            if phase_delta < -0.5:
                phase_delta += 1.0
            elif phase_delta > 0.5:
                phase_delta -= 1.0
            
            phase_changes.append(phase_delta / dt)
    
    if not phase_changes:
        print("❌ No valid phase changes")
        return None
    
    avg_phase_per_sec = statistics.mean(phase_changes)
    degrees_per_sec = abs(avg_phase_per_sec) * 360.0
    
    print(f"✅ VMC: {degrees_per_sec:.2f} degrees/sec ({len(measurements)} samples)")
    return degrees_per_sec

def test_launcher_speed(duration=15):
    """Quick Launcher speed test"""
    print(f"🎯 Testing Launcher for {duration}s...")
    
    run_script = Path(__file__).parent.parent / "run.py"
    venv_python = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
    
    process = subprocess.Popen(
        [str(venv_python), str(run_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    measurements = []
    start_time = time.time()
    
    def monitor():
        spiral_phase = 0.0
        rotation_speed = 4.0
        measurement_count = 0
        
        try:
            while time.time() - start_time < duration:
                line = process.stdout.readline()
                if not line:
                    break
                    
                if "rotation_debug" in line and "time=" in line:
                    try:
                        time_val = float(line.split("time=")[1].strip().split()[0])
                        spiral_phase = abs(time_val) % 1.0
                        measurements.append((time.time(), spiral_phase, rotation_speed))
                        measurement_count += 1
                        if measurement_count <= 5:  # Show first few measurements
                            print(f"  📊 Launcher sample {measurement_count}: phase={spiral_phase:.6f}, speed={rotation_speed}")
                    except Exception as e:
                        print(f"  ❌ Parse error: {e} in line: {line}")
                elif "rotation_debug" in line and "rotation_speed=" in line:
                    try:
                        rotation_speed = float(line.split("rotation_speed=")[1].strip().split()[0])
                    except:
                        pass
        except:
            pass
    
    monitor_thread = threading.Thread(target=monitor)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    time.sleep(duration)
    
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    
    print(f"  📈 Launcher collected {len(measurements)} measurements")
    
    if len(measurements) < 2:
        print("❌ Not enough measurements")
        return None
    
    # Calculate speed
    phase_changes = []
    for i in range(1, len(measurements)):
        curr_time, curr_phase, _ = measurements[i]
        prev_time, prev_phase, _ = measurements[i-1]
        
        dt = curr_time - prev_time
        if dt > 0:
            phase_delta = curr_phase - prev_phase
            if phase_delta < -0.5:
                phase_delta += 1.0
            elif phase_delta > 0.5:
                phase_delta -= 1.0
            
            phase_changes.append(phase_delta / dt)
    
    if not phase_changes:
        print("❌ No valid phase changes")
        return None
    
    avg_phase_per_sec = statistics.mean(phase_changes)
    degrees_per_sec = abs(avg_phase_per_sec) * 360.0
    
    print(f"✅ Launcher: {degrees_per_sec:.2f} degrees/sec ({len(measurements)} samples)")
    return degrees_per_sec

def main():
    print("🚀 Quick Speed Comparison Test")
    print("=" * 40)
    
    duration = 15  # seconds
    
    # Test VMC
    vmc_speed = test_vmc_speed(duration)
    
    print("\n⏳ Waiting 3 seconds...")
    time.sleep(3)
    
    # Test Launcher
    launcher_speed = test_launcher_speed(duration)
    
    print("\n📊 RESULTS:")
    print("=" * 40)
    
    if vmc_speed and launcher_speed:
        diff = abs(vmc_speed - launcher_speed)
        percent_diff = (diff / max(vmc_speed, launcher_speed)) * 100
        
        print(f"VMC Speed:      {vmc_speed:.2f} degrees/sec")
        print(f"Launcher Speed: {launcher_speed:.2f} degrees/sec")
        print(f"Difference:     {diff:.2f} degrees/sec ({percent_diff:.1f}%)")
        
        if percent_diff < 5.0:
            print("✅ SPEEDS MATCH! (< 5% difference)")
        else:
            print("❌ SIGNIFICANT SPEED DIFFERENCE! (> 5% difference)")
    else:
        print("❌ Test failed - insufficient data")

if __name__ == "__main__":
    main()