#!/usr/bin/env python3
"""Quick test to verify zoom measurement system"""

import sys
import time
import subprocess
from pathlib import Path

# Add MesmerGlass to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_zoom_measurement():
    """Run a short test to verify zoom measurements are working"""
    print("🔍 Testing Zoom Measurement System")
    print("=" * 50)
    
    # Test VMC for 15 seconds at speed 4
    print("\n📊 Testing VMC zoom measurement (15 seconds at speed 4)")
    
    try:
        # Start VMC with speed 4
        cmd = [sys.executable, "scripts/vmc_speed_test_mode.py"]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        start_time = time.time()
        zoom_measurements = []
        rotation_measurements = []
        
        while time.time() - start_time < 15:  # 15 second test
            line = process.stdout.readline()
            if not line:
                break
                
            # Parse zoom measurements
            if "[VMC zoom_debug] zoom_rate=" in line:
                try:
                    zoom_rate = float(line.split("zoom_rate=")[1].strip())
                    zoom_measurements.append(zoom_rate)
                except:
                    pass
            
            # Parse rotation speed
            elif "[VMC rotation_debug] rotation_speed=" in line:
                try:
                    rotation_speed = float(line.split("rotation_speed=")[1].strip())
                    rotation_measurements.append(rotation_speed)
                except:
                    pass
        
        process.terminate()
        
        # Analyze results
        if zoom_measurements and rotation_measurements:
            avg_zoom_rate = sum(zoom_measurements) / len(zoom_measurements)
            avg_rotation_speed = sum(rotation_measurements) / len(rotation_measurements)
            expected_zoom_rate = 0.005 * avg_rotation_speed
            zoom_accuracy = (avg_zoom_rate / expected_zoom_rate) * 100 if expected_zoom_rate > 0 else 0
            
            print(f"✅ Results:")
            print(f"   • Average Rotation Speed: {avg_rotation_speed:.1f}")
            print(f"   • Average Zoom Rate: {avg_zoom_rate:.6f}")
            print(f"   • Expected Zoom Rate: {expected_zoom_rate:.6f}")
            print(f"   • Zoom Accuracy: {zoom_accuracy:.1f}%")
            print(f"   • Measurements: {len(zoom_measurements)} zoom, {len(rotation_measurements)} rotation")
            
            if 95 <= zoom_accuracy <= 105:
                print("🎯 EXCELLENT: Zoom measurement system is working correctly!")
            elif 90 <= zoom_accuracy <= 110:
                print("✅ GOOD: Zoom measurement system is working well.")
            else:
                print("⚠️  WARNING: Zoom measurement may need calibration.")
                
        else:
            print("❌ FAILED: No measurements collected.")
            
    except Exception as e:
        print(f"❌ Error during test: {e}")

if __name__ == "__main__":
    test_zoom_measurement()