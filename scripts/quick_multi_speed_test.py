#!/usr/bin/env python3
"""
Quick Multi-Speed Test - Tests just 2 speeds for rapid verification
"""

import time
import statistics
import sys
import subprocess
import threading
from pathlib import Path

# Add MesmerGlass to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_speeds_quick():
    """Quick test of multiple speeds"""
    print("🚀 Quick Multi-Speed Test")
    print("Testing speeds: 4.0, 16.0")
    print("=" * 40)
    
    # Test VMC speed test mode
    print("\n🎯 Testing VMC...")
    vmc_script = Path(__file__).parent / "vmc_speed_test_mode.py"
    venv_python = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
    
    process = subprocess.Popen(
        [str(venv_python), str(vmc_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    measurements = {}
    current_speed = None
    speed_measurements = []
    start_time = time.time()
    
    try:
        while time.time() - start_time < 20:  # 20 second test
            line = process.stdout.readline()
            if not line:
                break
            
            # Detect speed changes
            if "[VMC_TEST]" in line and ("Changing speed to" in line or "Started with speed" in line):
                # Process previous speed
                if current_speed and len(speed_measurements) >= 3:
                    phases = [m[1] for m in speed_measurements]
                    times = [m[0] for m in speed_measurements]
                    
                    # Calculate speed
                    phase_changes = []
                    for i in range(1, len(phases)):
                        dt = times[i] - times[i-1]
                        if dt > 0:
                            phase_delta = phases[i] - phases[i-1]
                            if phase_delta < -0.5:
                                phase_delta += 1.0
                            elif phase_delta > 0.5:
                                phase_delta -= 1.0
                            phase_changes.append(phase_delta / dt)
                    
                    if phase_changes:
                        avg_phase_per_sec = statistics.mean(phase_changes)
                        degrees_per_sec = abs(avg_phase_per_sec) * 360.0
                        measurements[current_speed] = degrees_per_sec
                        print(f"  ✅ Speed {current_speed}: {degrees_per_sec:.1f} degrees/sec ({len(speed_measurements)} samples)")
                
                # Start new speed
                try:
                    current_speed = float(line.split()[-1])
                    speed_measurements = []
                    print(f"  🔄 Speed changed to {current_speed}")
                except:
                    pass
            
            # Collect measurements
            elif "[VMC rotation_debug]" in line and "time=" in line and current_speed:
                try:
                    time_val = float(line.split("time=")[1].strip())
                    spiral_phase = abs(time_val) % 1.0
                    speed_measurements.append((time.time(), spiral_phase))
                except:
                    pass
    
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    
    # Process final speed
    if current_speed and len(speed_measurements) >= 3:
        phases = [m[1] for m in speed_measurements]
        times = [m[0] for m in speed_measurements]
        
        phase_changes = []
        for i in range(1, len(phases)):
            dt = times[i] - times[i-1]
            if dt > 0:
                phase_delta = phases[i] - phases[i-1]
                if phase_delta < -0.5:
                    phase_delta += 1.0
                elif phase_delta > 0.5:
                    phase_delta -= 1.0
                phase_changes.append(phase_delta / dt)
        
        if phase_changes:
            avg_phase_per_sec = statistics.mean(phase_changes)
            degrees_per_sec = abs(avg_phase_per_sec) * 360.0
            measurements[current_speed] = degrees_per_sec
            print(f"  ✅ Speed {current_speed}: {degrees_per_sec:.1f} degrees/sec ({len(speed_measurements)} samples)")
    
    print(f"\n📊 VMC Results: {measurements}")
    
    # Calculate expected vs actual
    print("\n📈 Speed Analysis:")
    for speed, measured in measurements.items():
        expected = 21.6 * (speed / 4.0)  # Baseline 21.6 deg/sec at speed=4
        accuracy = (measured / expected) * 100
        print(f"  Speed {speed}: Expected {expected:.1f}°/s, Measured {measured:.1f}°/s, Accuracy {accuracy:.1f}%")

if __name__ == "__main__":
    test_speeds_quick()