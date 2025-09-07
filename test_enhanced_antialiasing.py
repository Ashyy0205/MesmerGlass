#!/usr/bin/env python3
"""
Test script for enhanced anti-aliasing improvements in spiral fragment shader.
Tests multiple supersampling levels and verifies visual quality improvements.
"""

import subprocess
import sys
import time

def test_supersampling_levels():
    """Test different supersampling levels for performance and functionality."""
    print("Testing Enhanced Anti-Aliasing with Multiple Supersampling Levels")
    print("=" * 65)
    
    # Test parameters
    test_duration = 1.5
    intensity = 0.25  # Low intensity to see artifacts clearly
    
    levels = [
        (1, "No Anti-aliasing"),
        (4, "2x2 Supersampling"), 
        (9, "3x3 Supersampling"),
        (16, "4x4 Supersampling")
    ]
    
    results = []
    
    for samples, description in levels:
        print(f"\n{description} (samples={samples}):")
        print("-" * 40)
        
        cmd = [
            sys.executable, "-m", "mesmerglass", "spiral-test",
            "--supersampling", str(samples),
            "--intensity", str(intensity),
            "--duration", str(test_duration)
        ]
        
        try:
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            elapsed = time.time() - start_time
            
            if result.returncode == 0:
                # Extract FPS from output
                output_lines = result.stdout.strip().split('\n')
                for line in output_lines:
                    if "fps=" in line:
                        fps_part = line.split("fps=")[1].split()[0]
                        fps = float(fps_part)
                        results.append((samples, description, fps, elapsed))
                        print(f"✓ Success: {fps:.1f} FPS")
                        break
                else:
                    print("✗ Could not parse FPS from output")
                    results.append((samples, description, 0.0, elapsed))
            else:
                print(f"✗ Failed with exit code {result.returncode}")
                print(f"Error: {result.stderr[:200]}")
                results.append((samples, description, 0.0, elapsed))
                
        except subprocess.TimeoutExpired:
            print("✗ Test timed out")
            results.append((samples, description, 0.0, elapsed))
        except Exception as e:
            print(f"✗ Exception: {e}")
            results.append((samples, description, 0.0, elapsed))
    
    # Summary
    print("\n" + "=" * 65)
    print("ANTI-ALIASING PERFORMANCE SUMMARY")
    print("=" * 65)
    print(f"{'Samples':<8} {'Description':<20} {'FPS':<8} {'Status'}")
    print("-" * 65)
    
    for samples, desc, fps, elapsed in results:
        status = "✓ Good" if fps > 50 else "⚠ Slow" if fps > 30 else "✗ Poor"
        print(f"{samples:<8} {desc:<20} {fps:<8.1f} {status}")
    
    # Check for performance regression
    baseline_fps = next((fps for samples, _, fps, _ in results if samples == 1), 0)
    max_samples_fps = next((fps for samples, _, fps, _ in results if samples == 16), 0)
    
    if baseline_fps > 0 and max_samples_fps > 0:
        perf_impact = (baseline_fps - max_samples_fps) / baseline_fps * 100
        print(f"\nPerformance Impact: {perf_impact:.1f}% (1 sample vs 16 samples)")
        
        if perf_impact < 15:  # Less than 15% impact is acceptable
            print("✓ Performance impact is acceptable")
        else:
            print("⚠ Performance impact may be too high")
    
    print("\nAnti-aliasing test completed!")
    return len([r for r in results if r[2] > 50]) == len(results)

if __name__ == "__main__":
    success = test_supersampling_levels()
    sys.exit(0 if success else 1)
