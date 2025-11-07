#!/usr/bin/env python3
"""
Quick test to measure actual FPS and verify RPM calculation
"""
import subprocess
import time
import re
import sys
import os

# Add the parent directory to sys.path so we can import mesmerglass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mesmerglass.mesmerloom.spiral_speed import SpiralSpeedCalculator

def test_rpm_calculation():
    """Test the new RPM-based calculation"""
    print("🧮 Testing RPM calculation...")
    
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
    
    measurements = []
    frame_times = []
    start_time = time.time()
    last_measurement_time = None
    
    try:
        while time.time() - start_time < 5:  # 5 second test
            line = process.stdout.readline()
            if not line:
                break
            
            # Parse VMC debug output
            if "[VMC rotation_debug]" in line and "time=" in line:
                try:
                    time_part = line.split("time=")[1]
                    spiral_time = float(time_part.split()[0])
                    current_time = time.time()
                    
                    measurements.append((current_time, spiral_time, 16.0))
                    
                    # Measure frame time
                    if last_measurement_time is not None:
                        frame_time = current_time - last_measurement_time
                        frame_times.append(frame_time)
                    
                    last_measurement_time = current_time
                except:
                    pass
                    
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
    
    if len(measurements) < 3:
        print("  ❌ Not enough measurements")
        return
    
    print(f"  📊 Collected {len(measurements)} measurements in 5 seconds")
    
    # Calculate frame rate
    if frame_times:
        avg_frame_time = sum(frame_times) / len(frame_times)
        measured_fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
        print(f"  🎬 Measured FPS: {measured_fps:.1f} (expected: 60.0)")
    
    # Calculate phase changes
    phase_changes = []
    time_deltas = []
    
    for i in range(1, len(measurements)):
        curr_time, curr_phase, _ = measurements[i]
        prev_time, prev_phase, _ = measurements[i-1]
        
        dt = curr_time - prev_time
        if dt > 0:
            # Handle wraparound
            phase_delta = curr_phase - prev_phase
            if phase_delta < -0.5:
                phase_delta += 1.0
            elif phase_delta > 0.5:
                phase_delta -= 1.0
            
            phase_rate = abs(phase_delta) / dt
            phase_changes.append(phase_rate)
            time_deltas.append(dt)
    
    if not phase_changes:
        print("  ❌ No valid phase changes")
        return
    
    # Calculate statistics
    avg_phase_per_sec = sum(phase_changes) / len(phase_changes)
    degrees_per_sec = avg_phase_per_sec * 360.0
    
    # Expected for 16.0 RPM
    expected_degrees_per_sec = SpiralSpeedCalculator.rpm_to_degrees_per_second(16.0)
    accuracy = (degrees_per_sec / expected_degrees_per_sec) * 100 if expected_degrees_per_sec > 0 else 0
    
    avg_time_delta = sum(time_deltas) / len(time_deltas)
    effective_fps = 1.0 / avg_time_delta if avg_time_delta > 0 else 0
    
    print(f"  📏 Results:")
    print(f"    Measured: {degrees_per_sec:.1f}°/s")
    print(f"    Expected: {expected_degrees_per_sec:.1f}°/s") 
    print(f"    Accuracy: {accuracy:.1f}%")
    print(f"    Avg time delta: {avg_time_delta:.4f}s")
    print(f"    Effective FPS: {effective_fps:.1f}")
    
    # Show phase increment per measurement
    if len(measurements) >= 2:
        first_phase = measurements[0][1]
        second_phase = measurements[1][1] 
        phase_increment = abs(second_phase - first_phase)
        expected_increment = SpiralSpeedCalculator.rpm_to_phase_per_frame(16.0, measured_fps)
        
        print(f"  🔢 Phase increment:")
        print(f"    Measured: {phase_increment:.6f} per measurement")
        print(f"    Expected: {expected_increment:.6f} per frame at {measured_fps:.1f} FPS")

if __name__ == "__main__":
    test_rpm_calculation()