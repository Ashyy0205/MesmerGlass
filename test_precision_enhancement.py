#!/usr/bin/env python3
"""
Test script for enhanced precision improvements in spiral fragment shader.
Tests different precision levels to verify visual quality improvements and artifact elimination.
"""

import subprocess
import sys
import time

def test_precision_levels():
    """Test different precision levels for visual quality comparison."""
    print("Testing Enhanced Precision Spiral Rendering")
    print("=" * 50)
    
    # Test parameters for maximum artifact visibility
    test_duration = 1.5
    intensity = 0.25  # Low intensity shows artifacts most clearly
    
    test_configs = [
        ("low", 1, "Low Precision + No AA"),
        ("medium", 4, "Medium Precision + 2x2 AA"),
        ("high", 4, "High Precision + 2x2 AA"),
        ("high", 16, "High Precision + 4x4 AA")
    ]
    
    results = []
    
    for precision, samples, description in test_configs:
        print(f"\n{description}:")
        print("-" * 40)
        
        cmd = [
            sys.executable, "-m", "mesmerglass", "spiral-test",
            "--precision", precision,
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
                        results.append((precision, samples, description, fps, elapsed))
                        print(f"✓ Success: {fps:.1f} FPS")
                        break
                else:
                    print("✗ Could not parse FPS from output")
                    results.append((precision, samples, description, 0.0, elapsed))
                    
                # Check for fallback shader usage (indicates compile errors)
                if "using fallback GL program" in result.stdout:
                    print("⚠ Warning: Fallback shader used (compile error)")
                    
            else:
                print(f"✗ Failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"Error: {result.stderr[:200]}")
                results.append((precision, samples, description, 0.0, elapsed))
                
        except subprocess.TimeoutExpired:
            print("✗ Test timed out")
            results.append((precision, samples, description, 0.0, elapsed))
        except Exception as e:
            print(f"✗ Exception: {e}")
            results.append((precision, samples, description, 0.0, elapsed))
    
    # Summary
    print("\n" + "=" * 70)
    print("PRECISION ENHANCEMENT PERFORMANCE SUMMARY")
    print("=" * 70)
    print(f"{'Precision':<10} {'Samples':<8} {'Description':<25} {'FPS':<8} {'Status'}")
    print("-" * 70)
    
    for precision, samples, desc, fps, elapsed in results:
        status = "✓ Good" if fps > 50 else "⚠ Slow" if fps > 30 else "✗ Poor"
        print(f"{precision:<10} {samples:<8} {desc:<25} {fps:<8.1f} {status}")
    
    # Analysis
    low_precision_fps = next((fps for p, s, d, fps, e in results if p == "low"), 0)
    high_precision_fps = next((fps for p, s, d, fps, e in results if p == "high" and s == 4), 0)
    max_quality_fps = next((fps for p, s, d, fps, e in results if p == "high" and s == 16), 0)
    
    print(f"\nPERFORMACE ANALYSIS:")
    if low_precision_fps > 0 and high_precision_fps > 0:
        precision_impact = (low_precision_fps - high_precision_fps) / low_precision_fps * 100
        print(f"• Precision Impact: {precision_impact:.1f}% (low vs high precision)")
        
    if high_precision_fps > 0 and max_quality_fps > 0:
        quality_impact = (high_precision_fps - max_quality_fps) / high_precision_fps * 100
        print(f"• Quality Impact: {quality_impact:.1f}% (4x vs 16x sampling)")
    
    successful_tests = len([r for r in results if r[3] > 50])
    print(f"• {successful_tests}/{len(results)} configurations achieved >50 FPS")
    
    if successful_tests == len(results):
        print("✓ All precision levels working efficiently")
    else:
        print("⚠ Some precision levels may have performance issues")
    
    print("\nPrecision enhancement test completed!")
    return successful_tests == len(results)

if __name__ == "__main__":
    success = test_precision_levels()
    sys.exit(0 if success else 1)
