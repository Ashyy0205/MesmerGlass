#!/usr/bin/env python3
"""
Quick test of corrected phase calculation
"""
import subprocess
import time
import re
import statistics
from typing import List, Tuple

def test_corrected_phase_calculation():
    """Test corrected phase measurement on VMC"""
    print("🔧 Testing corrected phase calculation...")
    
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
    
    measurements = []  # (time, phase, rotation_speed)
    start_time = time.time()
    
    try:
        while time.time() - start_time < 10:  # 10 second test
            line = process.stdout.readline()
            if not line:
                break
            
            # Parse phase with corrected logic  
            if "[VMC rotation_debug]" in line and "time=" in line:
                try:
                    # Extract spiral time (which equals phase for VMC)
                    time_part = line.split("time=")[1]
                    spiral_time = float(time_part.split()[0])  # Take only the first token after time=
                    
                    # VMC time equals phase, so phase = spiral_time
                    phase_val = spiral_time
                    
                    measurements.append((spiral_time, phase_val, 16.0))  # Use spiral time instead of system time
                except:
                    pass
                    
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
    
    if len(measurements) < 3:
        print("  ❌ Not enough measurements collected")
        return
    
    # Apply corrected phase calculation
    phase_changes = []
    
    for i in range(1, len(measurements)):
        curr_time, curr_phase, curr_speed = measurements[i]
        prev_time, prev_phase, prev_speed = measurements[i-1]
        
        dt = curr_time - prev_time
        if dt > 0:
            # Calculate phase change with proper wraparound handling
            phase_delta = curr_phase - prev_phase
            
            # Handle wraparound: if phase goes from ~1.0 to ~0.0, that's forward motion
            if phase_delta < -0.5:  # Wrapped forward (e.g., 0.9 -> 0.1)
                phase_delta += 1.0
            elif phase_delta > 0.5:  # Wrapped backward (e.g., 0.1 -> 0.9) 
                phase_delta -= 1.0
            
            # Convert to positive rotation rate (phase change per second)
            phase_rate = abs(phase_delta) / dt
            phase_changes.append(phase_rate)
    
    if not phase_changes:
        print("  ❌ No valid phase changes calculated")
        return
    
    # Calculate statistics
    avg_phase_per_sec = statistics.mean(phase_changes)
    degrees_per_sec = avg_phase_per_sec * 360.0
    rotations_per_sec = avg_phase_per_sec
    
    # Expected for 16.0 RPM: 16/60 = 0.2667 rotations/sec = 96°/sec
    expected_rotations_per_sec = 16.0 / 60.0
    expected_degrees_per_sec = expected_rotations_per_sec * 360.0
    
    accuracy = (rotations_per_sec / expected_rotations_per_sec) * 100 if expected_rotations_per_sec > 0 else 0
    
    print(f"  📊 Corrected Results:")
    print(f"    Measurements collected: {len(measurements)}")
    print(f"    Phase changes calculated: {len(phase_changes)}")
    print(f"    Average rotations/sec: {rotations_per_sec:.6f}")
    print(f"    Average degrees/sec: {degrees_per_sec:.2f}")
    print(f"    Expected rotations/sec: {expected_rotations_per_sec:.6f}")
    print(f"    Expected degrees/sec: {expected_degrees_per_sec:.2f}")
    print(f"    Accuracy: {accuracy:.1f}%")
    
    # Show some example phase transitions  
    print(f"  📝 Example phase transitions:")
    for i in range(min(5, len(measurements)-1)):
        curr_time, curr_phase, _ = measurements[i+1]
        prev_time, prev_phase, _ = measurements[i]
        phase_delta = curr_phase - prev_phase
        dt = curr_time - prev_time
        print(f"    {prev_phase:.6f} → {curr_phase:.6f} (Δ={phase_delta:.6f}, dt={dt:.3f}s)")

if __name__ == "__main__":
    test_corrected_phase_calculation()