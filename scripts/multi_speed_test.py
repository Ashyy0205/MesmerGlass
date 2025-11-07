#!/usr/bin/env python3
"""
Multi-Speed Test - Tests VMC and Launcher at different rotation speeds
=====================================================================

Tests rotation speeds: 4, 8, 16, 24 (and optionally 32, 40)
Automatically changes speed during test and measures accuracy at each level.
"""

import time
import math
import statistics
import sys
import json
from pathlib import Path
import subprocess
import threading
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

# Add MesmerGlass to path
sys.path.insert(0, str(Path(__file__).parent.parent))

@dataclass
class SpeedTestResult:
    """Results for a single speed test"""
    target_speed: float
    measured_degrees_per_sec: float
    measured_rotations_per_sec: float
    measured_zoom_rate: float
    expected_zoom_rate: float
    zoom_accuracy_percentage: float
    sample_count: int
    duration: float
    accuracy_percentage: float
    speed_consistency: float  # std dev
    zoom_consistency: float  # zoom std dev

class MultiSpeedTester:
    """Tests multiple rotation speeds automatically"""
    
    def __init__(self):
        self.test_speeds = [4.0, 8.0, 16.0, 24.0]  # Target rotation speeds
        self.test_duration_per_speed = 8.0  # seconds per speed test
        self.transition_time = 2.0  # seconds to wait between speed changes
        
    def calculate_expected_degrees_per_sec(self, rotation_speed: float) -> float:
        """Calculate expected degrees per second for a given rotation speed"""
        # Based on the Trance formula and spiral parameters
        # rotation_speed=4.0 is baseline, higher values are proportionally faster
        # Empirical measurement shows ~21.6 degrees/sec at speed=4.0
        baseline_degrees_per_sec = 21.6  # Measured baseline for speed=4.0
        return baseline_degrees_per_sec * (rotation_speed / 4.0)
    
    def calculate_expected_zoom_rate(self, rotation_speed: float) -> float:
        """Calculate expected zoom rate for a given rotation speed"""
        # Based on empirical observation from VMC:
        # rotation_speed=4.0 produces zoom_rate=0.020000
        # This suggests zoom_rate = 0.005 * rotation_speed
        return 0.005 * rotation_speed
    
    def test_vmc_multi_speed(self) -> Dict[float, SpeedTestResult]:
        """Test VMC at multiple speeds"""
        print(f"[TARGET] Testing VMC at speeds: {self.test_speeds}")
        
        # Start VMC in speed test mode
        vmc_test_script = Path(__file__).parent / "vmc_speed_test_mode.py"
        venv_python = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
        
        process = subprocess.Popen(
            [str(venv_python), str(vmc_test_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        results = {}
        
        try:
            # Wait for VMC to start up
            print("  [WAIT] Waiting for VMC startup...")
            time.sleep(5)
            
            # Monitor all speeds automatically (VMC will cycle through them)
            total_duration = len(self.test_speeds) * (self.test_duration_per_speed + self.transition_time)
            results = self._monitor_automatic_speed_changes_vmc(process, total_duration)
            
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        
        return results
    
    def test_launcher_multi_speed(self) -> Dict[float, SpeedTestResult]:
        """Test Launcher at multiple speeds"""
        print(f"[TARGET] Testing Launcher at speeds: {self.test_speeds}")
        
        # Start Launcher in speed test mode
        launcher_test_script = Path(__file__).parent / "launcher_speed_test_mode.py"
        venv_python = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
        
        process = subprocess.Popen(
            [str(venv_python), str(launcher_test_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        results = {}
        
        try:
            # Wait for Launcher to start up
            print("  [WAIT] Waiting for Launcher startup...")
            time.sleep(8)  # Launcher takes longer to start
            
            # Monitor all speeds automatically (Launcher will cycle through them)
            total_duration = len(self.test_speeds) * (self.test_duration_per_speed + self.transition_time)
            results = self._monitor_automatic_speed_changes_launcher(process, total_duration)
            
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        
        return results
    
    def _monitor_automatic_speed_changes_vmc(self, process, total_duration: float) -> Dict[float, SpeedTestResult]:
        """Monitor VMC as it automatically cycles through speeds"""
        results = {}
        current_speed_measurements = []  # (timestamp, spiral_phase, rotation_speed, zoom_level, zoom_rate)
        current_speed = None
        last_speed_change_time = time.time()
        start_time = time.time()
        
        # Track current values for collecting complete measurements
        current_zoom_level = 1.0
        current_zoom_rate = 0.0
        
        print("  [CHART] Monitoring automatic speed changes...")
        
        try:
            while time.time() - start_time < total_duration:
                line = process.stdout.readline()
                if not line:
                    break
                
                # Detect speed changes
                if "[VMC_TEST] Changing speed to" in line or "[VMC_TEST] Started with speed" in line:
                    # Process previous speed if we have measurements
                    if current_speed is not None and current_speed_measurements:
                        result = self._analyze_measurements(current_speed_measurements, current_speed)
                        if result:
                            results[current_speed] = result
                            expected = self.calculate_expected_degrees_per_sec(current_speed)
                            accuracy = (result.measured_degrees_per_sec / expected) * 100
                            print(f"    [OK] Speed {current_speed}: {result.measured_degrees_per_sec:.1f}°/s ({accuracy:.1f}% accuracy, {len(current_speed_measurements)} samples)")
                    
                    # Extract new speed
                    try:
                        new_speed = float(line.split()[-1])
                        current_speed = new_speed
                        current_speed_measurements = []
                        last_speed_change_time = time.time()
                        print(f"  [CYCLE] Detected speed change to {new_speed}")
                    except:
                        pass
                
                # Collect rotation measurements for current speed
                elif "[VMC rotation_debug]" in line and "time=" in line and current_speed is not None:
                    # Only collect measurements after a brief settling period
                    if time.time() - last_speed_change_time > 1.0:
                        try:
                            # Extract spiral time (which equals phase for VMC)
                            time_part = line.split("time=")[1]
                            spiral_time = float(time_part.split()[0])  # Take only the first token after time=
                            
                            # VMC time equals phase, so phase = spiral_time
                            phase_val = spiral_time
                            
                            # Use the spiral time instead of system time for accurate measurement
                            current_speed_measurements.append((spiral_time, phase_val, current_speed, current_zoom_level, current_zoom_rate))
                        except:
                            pass
                
                # Update zoom level tracking
                elif "[VMC zoom_debug]" in line and "zoom_level=" in line:
                    try:
                        zoom_part = line.split("zoom_level=")[1]
                        current_zoom_level = float(zoom_part.split()[0])  # Take only the first token
                    except:
                        pass
                
                # Update zoom rate tracking  
                elif "[VMC zoom_debug]" in line and "zoom_rate=" in line:
                    try:
                        zoom_rate_part = line.split("zoom_rate=")[1]
                        current_zoom_rate = float(zoom_rate_part.split()[0])  # Take only the first token
                    except:
                        pass
        
        except Exception as e:
            print(f"  [FAIL] Monitoring error: {e}")
        
        # Process final speed
        if current_speed is not None and current_speed_measurements:
            result = self._analyze_measurements(current_speed_measurements, current_speed)
            if result:
                results[current_speed] = result
                expected = self.calculate_expected_degrees_per_sec(current_speed)
                accuracy = (result.measured_degrees_per_sec / expected) * 100
                print(f"    [OK] Speed {current_speed}: {result.measured_degrees_per_sec:.1f}°/s ({accuracy:.1f}% accuracy, {len(current_speed_measurements)} samples)")
        
        return results
    
    def _monitor_automatic_speed_changes_launcher(self, process, total_duration: float) -> Dict[float, SpeedTestResult]:
        """Monitor Launcher as it automatically cycles through speeds"""
        results = {}
        current_speed_measurements = []  # (timestamp, spiral_phase, rotation_speed, zoom_level, zoom_rate)
        current_speed = None
        last_speed_change_time = time.time()
        start_time = time.time()
        
        # Track current values for collecting complete measurements
        current_zoom_level = 1.0
        current_zoom_rate = 0.0
        
        print("  [CHART] Monitoring automatic speed changes...")
        
        try:
            while time.time() - start_time < total_duration:
                line = process.stdout.readline()
                if not line:
                    break
                
                # Detect speed changes
                if "[LAUNCHER_TEST] Changing speed to" in line or "[LAUNCHER_TEST] Started with speed" in line:
                    # Process previous speed if we have measurements
                    if current_speed is not None and current_speed_measurements:
                        result = self._analyze_measurements(current_speed_measurements, current_speed)
                        if result:
                            results[current_speed] = result
                            expected = self.calculate_expected_degrees_per_sec(current_speed)
                            accuracy = (result.measured_degrees_per_sec / expected) * 100
                            print(f"    [OK] Speed {current_speed}: {result.measured_degrees_per_sec:.1f}°/s ({accuracy:.1f}% accuracy, {len(current_speed_measurements)} samples)")
                    
                    # Extract new speed
                    try:
                        new_speed = float(line.split()[-1])
                        current_speed = new_speed
                        current_speed_measurements = []
                        last_speed_change_time = time.time()
                        print(f"  [CYCLE] Detected speed change to {new_speed}")
                    except:
                        pass
                
                # Collect rotation measurements for current speed
                elif "[Launcher rotation_debug]" in line and "time=" in line and current_speed is not None:
                    # Only collect measurements after a brief settling period  
                    if time.time() - last_speed_change_time > 1.0:
                        try:
                            # Extract spiral time (which equals phase for Launcher)
                            time_part = line.split("time=")[1]
                            spiral_time = float(time_part.split()[0])  # Take only the first token after time=
                            
                            # Launcher time equals phase, so phase = spiral_time
                            phase_val = spiral_time
                            
                            # Use the spiral time instead of system time for accurate measurement
                            current_speed_measurements.append((spiral_time, phase_val, current_speed, current_zoom_level, current_zoom_rate))
                        except:
                            pass
                
                # Update zoom level tracking
                elif "zoom_debug" in line and "zoom_level=" in line:
                    try:
                        zoom_part = line.split("zoom_level=")[1]
                        current_zoom_level = float(zoom_part.split()[0])  # Take only the first token
                    except:
                        pass
                
                # Update zoom rate tracking
                elif "zoom_debug" in line and "zoom_rate=" in line:
                    try:
                        zoom_rate_part = line.split("zoom_rate=")[1]
                        current_zoom_rate = float(zoom_rate_part.split()[0])  # Take only the first token
                    except:
                        pass
        
        except Exception as e:
            print(f"  [FAIL] Monitoring error: {e}")
        
        # Process final speed
        if current_speed is not None and current_speed_measurements:
            result = self._analyze_measurements(current_speed_measurements, current_speed)
            if result:
                results[current_speed] = result
                expected = self.calculate_expected_degrees_per_sec(current_speed)
                accuracy = (result.measured_degrees_per_sec / expected) * 100
                print(f"    [OK] Speed {current_speed}: {result.measured_degrees_per_sec:.1f}°/s ({accuracy:.1f}% accuracy, {len(current_speed_measurements)} samples)")
        
        return results
        """Test VMC at a single speed"""
        measurements = []
        start_time = time.time()
        current_rotation_speed = 4.0
        
        # Monitor for the test duration
        while time.time() - start_time < self.test_duration_per_speed:
            try:
                line = process.stdout.readline()
                if not line:
                    break
                
                # Parse VMC debug output
                if "[VMC rotation_debug]" in line and "time=" in line:
                    try:
                        time_val = float(line.split("time=")[1].strip())
                        spiral_phase = abs(time_val) % 1.0
                        measurements.append((time.time(), spiral_phase, current_rotation_speed))
                    except:
                        pass
                elif "[VMC rotation_debug]" in line and "rotation_speed=" in line:
                    try:
                        current_rotation_speed = float(line.split("rotation_speed=")[1].strip())
                    except:
                        pass
            except:
                break
        
        return self._analyze_measurements(measurements, target_speed)
    
    def _test_single_speed_launcher(self, process, target_speed: float) -> Optional[SpeedTestResult]:
        """Test Launcher at a single speed"""
        measurements = []
        start_time = time.time()
        current_rotation_speed = 4.0
        
        # Monitor for the test duration
        while time.time() - start_time < self.test_duration_per_speed:
            try:
                line = process.stdout.readline()
                if not line:
                    break
                
                # Parse Launcher debug output
                if "rotation_debug" in line and "time=" in line:
                    try:
                        time_val = float(line.split("time=")[1].strip().split()[0])
                        spiral_phase = abs(time_val) % 1.0
                        measurements.append((time.time(), spiral_phase, current_rotation_speed))
                    except:
                        pass
                elif "rotation_debug" in line and "rotation_speed=" in line:
                    try:
                        current_rotation_speed = float(line.split("rotation_speed=")[1].strip().split()[0])
                    except:
                        pass
            except:
                break
        
        return self._analyze_measurements(measurements, target_speed)
    
    def _analyze_measurements(self, measurements: List[Tuple[float, float, float, float, float]], target_speed: float) -> Optional[SpeedTestResult]:
        """Analyze measurements and calculate rotation and zoom speeds"""
        if len(measurements) < 3:
            return None
        
        # Calculate phase changes for rotation
        phase_changes = []
        speeds = []
        zoom_rates = []
        zoom_levels = []
        
        for i in range(1, len(measurements)):
            curr_time, curr_phase, curr_speed, curr_zoom_level, curr_zoom_rate = measurements[i]
            prev_time, prev_phase, prev_speed, prev_zoom_level, prev_zoom_rate = measurements[i-1]
            
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
                speeds.append(curr_speed)
                zoom_rates.append(curr_zoom_rate)
                zoom_levels.append(curr_zoom_level)
        
        if not phase_changes:
            return None
        
        # Calculate rotation statistics
        avg_phase_per_sec = statistics.mean(phase_changes)
        degrees_per_sec = abs(avg_phase_per_sec) * 360.0
        rotations_per_sec = abs(avg_phase_per_sec)
        
        # Calculate rotation accuracy vs expected speed
        expected_degrees = self.calculate_expected_degrees_per_sec(target_speed)
        accuracy = (degrees_per_sec / expected_degrees) * 100 if expected_degrees > 0 else 0
        
        # Calculate rotation consistency
        consistency = statistics.stdev(phase_changes) if len(phase_changes) > 1 else 0
        
        # Calculate zoom statistics
        avg_zoom_rate = statistics.mean(zoom_rates) if zoom_rates else 0
        expected_zoom_rate = self.calculate_expected_zoom_rate(target_speed)
        zoom_accuracy = (avg_zoom_rate / expected_zoom_rate) * 100 if expected_zoom_rate > 0 else 0
        zoom_consistency = statistics.stdev(zoom_rates) if len(zoom_rates) > 1 else 0
        
        return SpeedTestResult(
            target_speed=target_speed,
            measured_degrees_per_sec=degrees_per_sec,
            measured_rotations_per_sec=rotations_per_sec,
            measured_zoom_rate=avg_zoom_rate,
            expected_zoom_rate=expected_zoom_rate,
            zoom_accuracy_percentage=zoom_accuracy,
            sample_count=len(measurements),
            duration=measurements[-1][0] - measurements[0][0] if measurements else 0,
            accuracy_percentage=accuracy,
            speed_consistency=consistency,
            zoom_consistency=zoom_consistency
        )

def compare_multi_speed_results(vmc_results: Dict[float, SpeedTestResult], 
                               launcher_results: Dict[float, SpeedTestResult]) -> Dict:
    """Compare multi-speed results between VMC and Launcher"""
    comparison = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_speeds": list(vmc_results.keys()),
        "speed_comparisons": {},
        "overall_accuracy": {},
        "consistency_analysis": {}
    }
    
    for speed in vmc_results.keys():
        if speed in launcher_results:
            vmc_result = vmc_results[speed]
            launcher_result = launcher_results[speed]
            
            # Rotation speed comparison
            speed_diff = abs(vmc_result.measured_degrees_per_sec - launcher_result.measured_degrees_per_sec)
            max_speed = max(vmc_result.measured_degrees_per_sec, launcher_result.measured_degrees_per_sec)
            percentage_diff = (speed_diff / max_speed) * 100 if max_speed > 0 else 0
            
            # Zoom rate comparison
            zoom_diff = abs(vmc_result.measured_zoom_rate - launcher_result.measured_zoom_rate)
            max_zoom = max(abs(vmc_result.measured_zoom_rate), abs(launcher_result.measured_zoom_rate))
            zoom_percentage_diff = (zoom_diff / max_zoom) * 100 if max_zoom > 0 else 0
            
            comparison["speed_comparisons"][str(speed)] = {
                "vmc_degrees_per_sec": vmc_result.measured_degrees_per_sec,
                "launcher_degrees_per_sec": launcher_result.measured_degrees_per_sec,
                "difference_degrees_per_sec": speed_diff,
                "percentage_difference": percentage_diff,
                "vmc_accuracy": vmc_result.accuracy_percentage,
                "launcher_accuracy": launcher_result.accuracy_percentage,
                "match_status": "MATCH" if percentage_diff < 5.0 else "MISMATCH",
                "vmc_zoom_rate": vmc_result.measured_zoom_rate,
                "launcher_zoom_rate": launcher_result.measured_zoom_rate,
                "zoom_difference": zoom_diff,
                "zoom_percentage_difference": zoom_percentage_diff,
                "vmc_zoom_accuracy": vmc_result.zoom_accuracy_percentage,
                "launcher_zoom_accuracy": launcher_result.zoom_accuracy_percentage,
                "zoom_match_status": "MATCH" if zoom_percentage_diff < 10.0 else "MISMATCH",
                "vmc_consistency": vmc_result.speed_consistency,
                "launcher_consistency": launcher_result.speed_consistency
            }
    
    # Overall accuracy analysis
    vmc_accuracies = [r.accuracy_percentage for r in vmc_results.values()]
    launcher_accuracies = [r.accuracy_percentage for r in launcher_results.values()]
    
    comparison["overall_accuracy"] = {
        "vmc_average_accuracy": statistics.mean(vmc_accuracies) if vmc_accuracies else 0,
        "launcher_average_accuracy": statistics.mean(launcher_accuracies) if launcher_accuracies else 0,
        "vmc_accuracy_std": statistics.stdev(vmc_accuracies) if len(vmc_accuracies) > 1 else 0,
        "launcher_accuracy_std": statistics.stdev(launcher_accuracies) if len(launcher_accuracies) > 1 else 0
    }
    
    return comparison

def generate_multi_speed_report(comparison: Dict, vmc_results: Dict, launcher_results: Dict) -> str:
    """Generate detailed multi-speed comparison report"""
    
    report = f"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                   MESMERGLASS MULTI-SPEED MEASUREMENT REPORT                 ║
║                              {comparison['timestamp']}                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣

[TARGET] MULTI-SPEED TEST SUMMARY
• Test Speeds: {', '.join(map(str, comparison['test_speeds']))}
• Total Measurements: VMC={sum(r.sample_count for r in vmc_results.values())}, Launcher={sum(r.sample_count for r in launcher_results.values())}

🌀 ROTATION SPEED COMPARISON
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ Speed │ VMC °/s    │ Launcher °/s │ Diff °/s │ Diff % │ VMC Acc │ Launch Acc │ Status │
├─────────────────────────────────────────────────────────────────────────────────────┤"""
    
    for speed_str, comp in comparison["speed_comparisons"].items():
        speed = float(speed_str)
        vmc_speed = comp["vmc_degrees_per_sec"]
        launcher_speed = comp["launcher_degrees_per_sec"]
        diff_speed = comp["difference_degrees_per_sec"]
        diff_percent = comp["percentage_difference"]
        vmc_acc = comp["vmc_accuracy"]
        launcher_acc = comp["launcher_accuracy"]
        status = comp["match_status"]
        
        status_icon = "[OK]" if status == "MATCH" else "[FAIL]"
        
        report += f"\n│ {speed:5.0f} │ {vmc_speed:10.2f} │ {launcher_speed:12.2f} │ {diff_speed:8.2f} │ {diff_percent:6.1f} │ {vmc_acc:7.1f} │ {launcher_acc:10.1f} │ {status_icon} {status:5} │"
    
    report += "\n└─────────────────────────────────────────────────────────────────────────────────────┘\n"
    
    # Add zoom comparison section
    report += """
[SEARCH] ZOOM SPEED COMPARISON
┌────────────────────────────────────────────────────────────────────────────────────┐
│ Speed │ VMC Zoom   │ Launcher Zoom│ Diff     │ Diff % │ VMC ZAcc│ Launch ZAcc│ Status │
├────────────────────────────────────────────────────────────────────────────────────┤"""
    
    for speed_str, comp in comparison["speed_comparisons"].items():
        speed = float(speed_str)
        vmc_zoom = comp.get("vmc_zoom_rate", 0)
        launcher_zoom = comp.get("launcher_zoom_rate", 0)
        zoom_diff = comp.get("zoom_difference", 0)
        zoom_percent = comp.get("zoom_percentage_difference", 0)
        vmc_zacc = comp.get("vmc_zoom_accuracy", 0)
        launcher_zacc = comp.get("launcher_zoom_accuracy", 0)
        zoom_status = comp.get("zoom_match_status", "UNKNOWN")
        
        zoom_status_icon = "[OK]" if zoom_status == "MATCH" else "[FAIL]"
        
        report += f"\n│ {speed:5.0f} │ {vmc_zoom:10.5f} │ {launcher_zoom:12.5f} │ {zoom_diff:8.5f} │ {zoom_percent:6.1f} │ {vmc_zacc:7.1f} │ {launcher_zacc:10.1f} │ {zoom_status_icon} {zoom_status:5} │"
    
    report += "\n└────────────────────────────────────────────────────────────────────────────────────┘\n"
    
    # Overall assessment
    all_match = all(comp["match_status"] == "MATCH" for comp in comparison["speed_comparisons"].values())
    vmc_avg_acc = comparison["overall_accuracy"]["vmc_average_accuracy"]
    launcher_avg_acc = comparison["overall_accuracy"]["launcher_average_accuracy"]
    
    report += f"""
[CHART] OVERALL ACCURACY ANALYSIS
• VMC Average Accuracy: {vmc_avg_acc:.1f}% (std: {comparison["overall_accuracy"]["vmc_accuracy_std"]:.1f}%)
• Launcher Average Accuracy: {launcher_avg_acc:.1f}% (std: {comparison["overall_accuracy"]["launcher_accuracy_std"]:.1f}%)

[TARGET] MULTI-SPEED CONCLUSION
"""
    
    # Check rotation and zoom match status
    speed_comparisons = comparison.get("speed_comparisons", {})
    if len(speed_comparisons) > 0:
        all_rotation_match = all(comp["match_status"] == "MATCH" for comp in speed_comparisons.values())
        all_zoom_match = all(comp.get("zoom_match_status", "UNKNOWN") == "MATCH" for comp in speed_comparisons.values())
        rotation_match_pct = sum(1 for comp in speed_comparisons.values() if comp["match_status"] == "MATCH") / len(speed_comparisons)
        zoom_match_pct = sum(1 for comp in speed_comparisons.values() if comp.get("zoom_match_status", "UNKNOWN") == "MATCH") / len(speed_comparisons)
    else:
        all_rotation_match = False
        all_zoom_match = False
        rotation_match_pct = 0.0
        zoom_match_pct = 0.0
    
    if len(speed_comparisons) == 0:
        report += "[FAIL] FAILED: No speed comparisons available (Launcher may have failed to start or collect data)."
    elif all_rotation_match and all_zoom_match and min(vmc_avg_acc, launcher_avg_acc) > 95.0:
        report += "[OK] EXCELLENT: All rotation and zoom speeds match perfectly with high accuracy!"
    elif all_rotation_match and all_zoom_match:
        report += "[OK] GOOD: All rotation and zoom speeds match but some accuracy variation detected."
    elif rotation_match_pct >= 0.75 and zoom_match_pct >= 0.75:
        report += "[WARN]  PARTIAL: Most rotation and zoom speeds match but some discrepancies detected."
    elif rotation_match_pct >= 0.75:
        report += "[WARN]  ROTATION OK, ZOOM ISSUES: Rotation speeds match but zoom speed discrepancies detected."
    elif zoom_match_pct >= 0.75:
        report += "[WARN]  ZOOM OK, ROTATION ISSUES: Zoom speeds match but rotation speed discrepancies detected."
    else:
        report += "[FAIL] FAILED: Significant rotation and/or zoom speed differences detected across multiple speeds!"
    
    report += "\n\n╚═══════════════════════════════════════════════════════════════════════════════╝\n"
    
    return report

def main():
    """Run multi-speed comparison test"""
    print("MesmerGlass Multi-Speed Test")
    print("=" * 50)
    print("Testing rotation speeds: 4, 8, 16, 24")
    print("This will take approximately 2-3 minutes...")
    
    tester = MultiSpeedTester()
    
    # Test VMC
    print(f"\nTesting VMC across multiple speeds...")
    vmc_results = tester.test_vmc_multi_speed()
    print(f"VMC testing complete: {len(vmc_results)} speeds tested")
    
    # Wait between apps
    print("\n[WAIT] Waiting 5 seconds between applications...")
    time.sleep(5)
    
    # Test Launcher
    print(f"\n[CHART] Testing Launcher across multiple speeds...")
    launcher_results = tester.test_launcher_multi_speed()
    print(f"[OK] Launcher testing complete: {len(launcher_results)} speeds tested")
    
    # Compare results
    print("\n[GRAPH] Analyzing multi-speed results...")
    comparison = compare_multi_speed_results(vmc_results, launcher_results)
    
    # Generate report
    report = generate_multi_speed_report(comparison, vmc_results, launcher_results)
    print(report)
    
    # Save detailed results
    results_file = Path(__file__).parent / f"multi_speed_test_results_{int(time.time())}.json"
    detailed_results = {
        "comparison": comparison,
        "vmc_results": {str(k): {
            "target_speed": v.target_speed,
            "measured_degrees_per_sec": v.measured_degrees_per_sec,
            "measured_rotations_per_sec": v.measured_rotations_per_sec,
            "sample_count": v.sample_count,
            "duration": v.duration,
            "accuracy_percentage": v.accuracy_percentage,
            "speed_consistency": v.speed_consistency
        } for k, v in vmc_results.items()},
        "launcher_results": {str(k): {
            "target_speed": v.target_speed,
            "measured_degrees_per_sec": v.measured_degrees_per_sec,
            "measured_rotations_per_sec": v.measured_rotations_per_sec,
            "sample_count": v.sample_count,
            "duration": v.duration,
            "accuracy_percentage": v.accuracy_percentage,
            "speed_consistency": v.speed_consistency
        } for k, v in launcher_results.items()}
    }
    
    with open(results_file, 'w') as f:
        json.dump(detailed_results, f, indent=2)
    
    print(f"💾 Detailed results saved to: {results_file}")

if __name__ == "__main__":
    main()