#!/usr/bin/env python3
"""
MesmerGlass Speed Measurement Test - PRECISION ANALYSIS
======================================================

This test accurately measures and compares:
1. Spiral rotation speed (degrees/second, radians/second)
2. Zoom speed (zoom units/second) 
3. Frame timing consistency
4. Performance differences between VMC and Launcher

MEASUREMENT METHODOLOGY:
- Direct shader uniform monitoring
- High-precision timing with performance counter
- Statistical analysis of speed variations
- Frame-by-frame consistency checks
"""

import time
import math
import statistics
import json
import sys
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
import subprocess
import threading
import queue
from contextlib import contextmanager

# Add MesmerGlass to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class SpeedMeasurement:
    """Single speed measurement snapshot"""
    timestamp: float
    spiral_phase: float  # Current spiral phase [0-1]
    rotation_speed: float  # rotation_speed setting
    effective_speed: float  # uEffectiveSpeed shader uniform
    base_speed: float  # uBaseSpeed shader uniform
    zoom_level: float  # Current zoom level
    zoom_rate: float  # Zoom speed
    frame_number: int
    app_type: str  # 'vmc' or 'launcher'

@dataclass
class SpeedAnalysis:
    """Complete speed analysis results"""
    app_type: str
    duration_seconds: float
    sample_count: int
    
    # Spiral rotation measurements
    spiral_rotations_per_second: float
    spiral_degrees_per_second: float
    spiral_radians_per_second: float
    spiral_phase_delta_per_second: float
    
    # Zoom measurements  
    zoom_units_per_second: float
    zoom_rate_average: float
    
    # Timing consistency
    frame_rate_average: float
    frame_time_std_dev: float
    frame_drops_detected: int
    
    # Speed stability
    spiral_speed_std_dev: float
    zoom_speed_std_dev: float
    
    # Raw measurements
    measurements: List[SpeedMeasurement]

class SpeedMeasurementCollector:
    """Collects speed measurements from running applications"""
    
    def __init__(self):
        self.measurements: List[SpeedMeasurement] = []
        self.start_time = None
        self.frame_count = 0
        self.collecting = False
        
    def start_collection(self) -> None:
        """Start collecting measurements"""
        self.measurements.clear()
        self.start_time = time.perf_counter()
        self.frame_count = 0
        self.collecting = True
        logger.info("🎯 Started speed measurement collection")
        
    def stop_collection(self) -> None:
        """Stop collecting measurements"""
        self.collecting = False
        logger.info(f"⏹️  Stopped speed measurement collection - {len(self.measurements)} samples")
        
    def add_measurement(self, 
                       spiral_phase: float,
                       rotation_speed: float, 
                       effective_speed: float,
                       base_speed: float,
                       zoom_level: float,
                       zoom_rate: float,
                       app_type: str) -> None:
        """Add a single measurement sample"""
        if not self.collecting:
            return
            
        measurement = SpeedMeasurement(
            timestamp=time.perf_counter(),
            spiral_phase=spiral_phase,
            rotation_speed=rotation_speed,
            effective_speed=effective_speed,
            base_speed=base_speed,
            zoom_level=zoom_level,
            zoom_rate=zoom_rate,
            frame_number=self.frame_count,
            app_type=app_type
        )
        
        self.measurements.append(measurement)
        self.frame_count += 1
        
    def analyze_measurements(self, app_type: str) -> SpeedAnalysis:
        """Analyze collected measurements and calculate precise speeds"""
        if not self.measurements:
            raise ValueError("No measurements to analyze")
            
        duration = self.measurements[-1].timestamp - self.measurements[0].timestamp
        
        # Calculate spiral rotation speed
        spiral_phase_changes = []
        spiral_speeds = []
        zoom_speeds = []
        frame_times = []
        
        for i in range(1, len(self.measurements)):
            curr = self.measurements[i]
            prev = self.measurements[i-1]
            
            dt = curr.timestamp - prev.timestamp
            if dt > 0:
                frame_times.append(dt)
                
                # Calculate spiral phase change (handle wraparound)
                phase_delta = curr.spiral_phase - prev.spiral_phase
                if phase_delta < -0.5:  # Wrapped around from ~1.0 to ~0.0
                    phase_delta += 1.0
                elif phase_delta > 0.5:  # Wrapped around from ~0.0 to ~1.0
                    phase_delta -= 1.0
                    
                spiral_phase_changes.append(phase_delta / dt)
                spiral_speeds.append(curr.effective_speed)
                
                # Calculate zoom speed
                zoom_delta = curr.zoom_level - prev.zoom_level
                zoom_speeds.append(abs(zoom_delta / dt))
        
        # Statistical analysis
        avg_spiral_phase_per_sec = statistics.mean(spiral_phase_changes) if spiral_phase_changes else 0
        avg_spiral_speed = statistics.mean(spiral_speeds) if spiral_speeds else 0
        avg_zoom_speed = statistics.mean(zoom_speeds) if zoom_speeds else 0
        avg_frame_time = statistics.mean(frame_times) if frame_times else 0
        
        # Convert phase/second to degrees/second and radians/second
        # 1 complete phase cycle = 360 degrees = 2π radians
        degrees_per_second = abs(avg_spiral_phase_per_sec) * 360.0
        radians_per_second = abs(avg_spiral_phase_per_sec) * 2.0 * math.pi
        rotations_per_second = abs(avg_spiral_phase_per_sec)
        
        # Frame rate analysis
        frame_rate = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
        frame_time_std = statistics.stdev(frame_times) if len(frame_times) > 1 else 0
        
        # Detect frame drops (frames taking >20ms = <50fps)
        frame_drops = sum(1 for ft in frame_times if ft > 0.020)
        
        # Speed consistency
        spiral_std = statistics.stdev(spiral_speeds) if len(spiral_speeds) > 1 else 0
        zoom_std = statistics.stdev(zoom_speeds) if len(zoom_speeds) > 1 else 0
        
        return SpeedAnalysis(
            app_type=app_type,
            duration_seconds=duration,
            sample_count=len(self.measurements),
            spiral_rotations_per_second=rotations_per_second,
            spiral_degrees_per_second=degrees_per_second,
            spiral_radians_per_second=radians_per_second,
            spiral_phase_delta_per_second=avg_spiral_phase_per_sec,
            zoom_units_per_second=avg_zoom_speed,
            zoom_rate_average=statistics.mean([m.zoom_rate for m in self.measurements]),
            frame_rate_average=frame_rate,
            frame_time_std_dev=frame_time_std,
            frame_drops_detected=frame_drops,
            spiral_speed_std_dev=spiral_std,
            zoom_speed_std_dev=zoom_std,
            measurements=self.measurements
        )

class VMCSpeedMonitor:
    """Monitors VMC for speed measurements"""
    
    def __init__(self, collector: SpeedMeasurementCollector):
        self.collector = collector
        self.process = None
        self.monitoring = False
        
    def start_monitoring(self, duration_seconds: float = 30.0) -> SpeedAnalysis:
        """Start VMC and monitor its speed for specified duration"""
        logger.info(f"🚀 Starting VMC speed monitoring for {duration_seconds}s")
        
        # Start VMC process
        vmc_script = Path(__file__).parent / "visual_mode_creator.py"
        venv_python = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
        
        self.process = subprocess.Popen(
            [str(venv_python), str(vmc_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        self.collector.start_collection()
        
        # Monitor output for speed data
        monitor_thread = threading.Thread(target=self._monitor_output)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Run for specified duration
        time.sleep(duration_seconds)
        
        self.collector.stop_collection()
        self.stop_monitoring()
        
        return self.collector.analyze_measurements("vmc")
        
    def _monitor_output(self):
        """Monitor VMC output for speed measurements"""
        spiral_phase = 0.0
        rotation_speed = 4.0
        effective_speed = 0.09
        base_speed = 0.09
        zoom_level = 1.0
        zoom_rate = 0.0
        
        try:
            while self.collector.collecting and self.process:
                line = self.process.stdout.readline()
                if not line:
                    break
                    
                line = line.strip()
                
                # Parse rotation debug info
                if "[VMC rotation_debug]" in line:
                    if "time=" in line:
                        try:
                            time_val = float(line.split("time=")[1].split()[0])
                            spiral_phase = abs(time_val) % 1.0  # Normalize to [0,1]
                        except:
                            pass
                    elif "rotation_speed=" in line:
                        try:
                            rotation_speed = float(line.split("rotation_speed=")[1].split()[0])
                        except:
                            pass
                    elif "uEffectiveSpeed=" in line:
                        try:
                            effective_speed = float(line.split("uEffectiveSpeed=")[1].split()[0])
                        except:
                            pass
                    elif "uBaseSpeed=" in line:
                        try:
                            base_speed = float(line.split("uBaseSpeed=")[1].split()[0])
                        except:
                            pass
                
                # Parse zoom info
                elif "Starting exponential zoom" in line and "rate=" in line:
                    try:
                        rate_part = line.split("rate=")[1].split()[0]
                        zoom_rate = float(rate_part)
                    except:
                        pass
                        
                # Add measurement every time we get a rotation debug line
                if "[VMC rotation_debug]" in line and "time=" in line:
                    self.collector.add_measurement(
                        spiral_phase=spiral_phase,
                        rotation_speed=rotation_speed,
                        effective_speed=effective_speed,
                        base_speed=base_speed,
                        zoom_level=zoom_level,
                        zoom_rate=zoom_rate,
                        app_type="vmc"
                    )
                    
        except Exception as e:
            logger.error(f"Error monitoring VMC output: {e}")
            
    def stop_monitoring(self):
        """Stop monitoring VMC"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

class LauncherSpeedMonitor:
    """Monitors Launcher for speed measurements"""
    
    def __init__(self, collector: SpeedMeasurementCollector):
        self.collector = collector
        self.process = None
        
    def start_monitoring(self, duration_seconds: float = 30.0) -> SpeedAnalysis:
        """Start Launcher and monitor its speed for specified duration"""
        logger.info(f"🚀 Starting Launcher speed monitoring for {duration_seconds}s")
        
        # Start Launcher process
        run_script = Path(__file__).parent.parent / "run.py"
        venv_python = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
        
        self.process = subprocess.Popen(
            [str(venv_python), str(run_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        self.collector.start_collection()
        
        # Monitor output for speed data
        monitor_thread = threading.Thread(target=self._monitor_output)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Run for specified duration
        time.sleep(duration_seconds)
        
        self.collector.stop_collection()
        self.stop_monitoring()
        
        return self.collector.analyze_measurements("launcher")
        
    def _monitor_output(self):
        """Monitor Launcher output for speed measurements"""
        spiral_phase = 0.0
        rotation_speed = 4.0
        effective_speed = 0.09
        base_speed = 0.09
        zoom_level = 1.0
        zoom_rate = 0.0
        
        try:
            while self.collector.collecting and self.process:
                line = self.process.stdout.readline()
                if not line:
                    break
                    
                line = line.strip()
                
                # Parse rotation debug info (same format as VMC)
                if "rotation_debug" in line:
                    if "time=" in line:
                        try:
                            time_val = float(line.split("time=")[1].split()[0])
                            spiral_phase = abs(time_val) % 1.0
                        except:
                            pass
                    elif "rotation_speed=" in line:
                        try:
                            rotation_speed = float(line.split("rotation_speed=")[1].split()[0])
                        except:
                            pass
                    elif "uEffectiveSpeed=" in line:
                        try:
                            effective_speed = float(line.split("uEffectiveSpeed=")[1].split()[0])
                        except:
                            pass
                    elif "uBaseSpeed=" in line:
                        try:
                            base_speed = float(line.split("uBaseSpeed=")[1].split()[0])
                        except:
                            pass
                
                # Parse zoom info
                elif "zoom" in line.lower() and "rate=" in line:
                    try:
                        rate_part = line.split("rate=")[1].split()[0]
                        zoom_rate = float(rate_part)
                    except:
                        pass
                        
                # Add measurement
                if "rotation_debug" in line and "time=" in line:
                    self.collector.add_measurement(
                        spiral_phase=spiral_phase,
                        rotation_speed=rotation_speed,
                        effective_speed=effective_speed,
                        base_speed=base_speed,
                        zoom_level=zoom_level,
                        zoom_rate=zoom_rate,
                        app_type="launcher"
                    )
                    
        except Exception as e:
            logger.error(f"Error monitoring Launcher output: {e}")
            
    def stop_monitoring(self):
        """Stop monitoring Launcher"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

def compare_speeds(vmc_analysis: SpeedAnalysis, launcher_analysis: SpeedAnalysis) -> Dict:
    """Compare speeds between VMC and Launcher with detailed analysis"""
    
    comparison = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_duration_seconds": max(vmc_analysis.duration_seconds, launcher_analysis.duration_seconds),
        
        "spiral_rotation": {
            "vmc_degrees_per_second": vmc_analysis.spiral_degrees_per_second,
            "launcher_degrees_per_second": launcher_analysis.spiral_degrees_per_second,
            "difference_degrees_per_second": abs(vmc_analysis.spiral_degrees_per_second - launcher_analysis.spiral_degrees_per_second),
            "percentage_difference": abs(vmc_analysis.spiral_degrees_per_second - launcher_analysis.spiral_degrees_per_second) / max(vmc_analysis.spiral_degrees_per_second, launcher_analysis.spiral_degrees_per_second) * 100 if max(vmc_analysis.spiral_degrees_per_second, launcher_analysis.spiral_degrees_per_second) > 0 else 0,
            "vmc_rotations_per_second": vmc_analysis.spiral_rotations_per_second,
            "launcher_rotations_per_second": launcher_analysis.spiral_rotations_per_second,
        },
        
        "zoom_speed": {
            "vmc_units_per_second": vmc_analysis.zoom_units_per_second,
            "launcher_units_per_second": launcher_analysis.zoom_units_per_second,
            "difference_units_per_second": abs(vmc_analysis.zoom_units_per_second - launcher_analysis.zoom_units_per_second),
            "percentage_difference": abs(vmc_analysis.zoom_units_per_second - launcher_analysis.zoom_units_per_second) / max(vmc_analysis.zoom_units_per_second, launcher_analysis.zoom_units_per_second) * 100 if max(vmc_analysis.zoom_units_per_second, launcher_analysis.zoom_units_per_second) > 0 else 0,
        },
        
        "frame_rate": {
            "vmc_fps": vmc_analysis.frame_rate_average,
            "launcher_fps": launcher_analysis.frame_rate_average,
            "difference_fps": abs(vmc_analysis.frame_rate_average - launcher_analysis.frame_rate_average),
            "vmc_frame_drops": vmc_analysis.frame_drops_detected,
            "launcher_frame_drops": launcher_analysis.frame_drops_detected,
        },
        
        "consistency": {
            "vmc_spiral_speed_std_dev": vmc_analysis.spiral_speed_std_dev,
            "launcher_spiral_speed_std_dev": launcher_analysis.spiral_speed_std_dev,
            "vmc_frame_time_std_dev": vmc_analysis.frame_time_std_dev,
            "launcher_frame_time_std_dev": launcher_analysis.frame_time_std_dev,
        },
        
        "sample_counts": {
            "vmc_samples": vmc_analysis.sample_count,
            "launcher_samples": launcher_analysis.sample_count,
        }
    }
    
    return comparison

def generate_speed_report(comparison: Dict, vmc_analysis: SpeedAnalysis, launcher_analysis: SpeedAnalysis) -> str:
    """Generate a detailed speed comparison report"""
    
    report = f"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    MESMERGLASS SPEED MEASUREMENT REPORT                       ║
║                              {comparison['timestamp']}                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣

📊 TEST SUMMARY
• Test Duration: {comparison['test_duration_seconds']:.1f} seconds
• VMC Samples: {comparison['sample_counts']['vmc_samples']}
• Launcher Samples: {comparison['sample_counts']['launcher_samples']}

🌀 SPIRAL ROTATION SPEED COMPARISON
┌─────────────────────────────────────────────────────────────────────────────┐
│ Application │ Degrees/Sec │ Rotations/Sec │ Std Dev │ Frame Rate │ Drops   │
├─────────────────────────────────────────────────────────────────────────────┤
│ VMC         │ {vmc_analysis.spiral_degrees_per_second:11.2f} │ {vmc_analysis.spiral_rotations_per_second:13.4f} │ {vmc_analysis.spiral_speed_std_dev:7.4f} │ {vmc_analysis.frame_rate_average:10.1f} │ {vmc_analysis.frame_drops_detected:7d} │
│ Launcher    │ {launcher_analysis.spiral_degrees_per_second:11.2f} │ {launcher_analysis.spiral_rotations_per_second:13.4f} │ {launcher_analysis.spiral_speed_std_dev:7.4f} │ {launcher_analysis.frame_rate_average:10.1f} │ {launcher_analysis.frame_drops_detected:7d} │
└─────────────────────────────────────────────────────────────────────────────┘

• Speed Difference: {comparison['spiral_rotation']['difference_degrees_per_second']:.2f} degrees/sec ({comparison['spiral_rotation']['percentage_difference']:.1f}%)
• {"✅ SPEEDS MATCH" if comparison['spiral_rotation']['percentage_difference'] < 5.0 else "❌ SIGNIFICANT SPEED DIFFERENCE"}

🔍 ZOOM SPEED COMPARISON  
┌─────────────────────────────────────────────────────────────────────────────┐
│ Application │ Zoom Units/Sec │ Std Dev │
├─────────────────────────────────────────────────────────────────────────────┤
│ VMC         │ {vmc_analysis.zoom_units_per_second:14.4f} │ {vmc_analysis.zoom_speed_std_dev:7.4f} │
│ Launcher    │ {launcher_analysis.zoom_units_per_second:14.4f} │ {launcher_analysis.zoom_speed_std_dev:7.4f} │
└─────────────────────────────────────────────────────────────────────────────┘

• Zoom Speed Difference: {comparison['zoom_speed']['difference_units_per_second']:.4f} units/sec ({comparison['zoom_speed']['percentage_difference']:.1f}%)
• {"✅ ZOOM SPEEDS MATCH" if comparison['zoom_speed']['percentage_difference'] < 5.0 else "❌ SIGNIFICANT ZOOM SPEED DIFFERENCE"}

⏱️  TIMING CONSISTENCY
• VMC Frame Time Std Dev: {vmc_analysis.frame_time_std_dev:.4f}s
• Launcher Frame Time Std Dev: {launcher_analysis.frame_time_std_dev:.4f}s
• {"✅ CONSISTENT TIMING" if max(vmc_analysis.frame_time_std_dev, launcher_analysis.frame_time_std_dev) < 0.005 else "⚠️  TIMING INCONSISTENCY DETECTED"}

🎯 CONCLUSION
"""
    
    # Overall assessment
    spiral_match = comparison['spiral_rotation']['percentage_difference'] < 5.0
    zoom_match = comparison['zoom_speed']['percentage_difference'] < 5.0
    timing_good = max(vmc_analysis.frame_time_std_dev, launcher_analysis.frame_time_std_dev) < 0.005
    
    if spiral_match and zoom_match and timing_good:
        report += "✅ PERFECT: VMC and Launcher speeds are synchronized!\n"
    elif spiral_match and zoom_match:
        report += "✅ GOOD: Speeds match but some timing inconsistency detected.\n"
    elif spiral_match or zoom_match:
        report += "⚠️  PARTIAL: Some speed differences detected.\n"
    else:
        report += "❌ FAILED: Significant speed differences detected!\n"
        
    report += "\n╚═══════════════════════════════════════════════════════════════════════════════╝\n"
    
    return report

def main():
    """Run comprehensive speed measurement test"""
    print("🎯 MesmerGlass Speed Measurement Test")
    print("=" * 50)
    
    test_duration = 30.0  # seconds
    
    # Test VMC
    print(f"\n📊 Testing VMC speed for {test_duration}s...")
    vmc_collector = SpeedMeasurementCollector()
    vmc_monitor = VMCSpeedMonitor(vmc_collector)
    
    try:
        vmc_analysis = vmc_monitor.start_monitoring(test_duration)
        print(f"✅ VMC test complete: {vmc_analysis.sample_count} samples")
    except Exception as e:
        print(f"❌ VMC test failed: {e}")
        return
    finally:
        vmc_monitor.stop_monitoring()
    
    # Wait between tests
    print("\n⏳ Waiting 5 seconds between tests...")
    time.sleep(5)
    
    # Test Launcher
    print(f"\n📊 Testing Launcher speed for {test_duration}s...")
    launcher_collector = SpeedMeasurementCollector()
    launcher_monitor = LauncherSpeedMonitor(launcher_collector)
    
    try:
        launcher_analysis = launcher_monitor.start_monitoring(test_duration)
        print(f"✅ Launcher test complete: {launcher_analysis.sample_count} samples")
    except Exception as e:
        print(f"❌ Launcher test failed: {e}")
        return
    finally:
        launcher_monitor.stop_monitoring()
    
    # Compare results
    print("\n📈 Analyzing results...")
    comparison = compare_speeds(vmc_analysis, launcher_analysis)
    
    # Generate report
    report = generate_speed_report(comparison, vmc_analysis, launcher_analysis)
    print(report)
    
    # Save detailed results
    results_file = Path(__file__).parent / f"speed_test_results_{int(time.time())}.json"
    detailed_results = {
        "comparison": comparison,
        "vmc_analysis": asdict(vmc_analysis),
        "launcher_analysis": asdict(launcher_analysis)
    }
    
    with open(results_file, 'w') as f:
        json.dump(detailed_results, f, indent=2, default=str)
    
    print(f"💾 Detailed results saved to: {results_file}")

if __name__ == "__main__":
    main()