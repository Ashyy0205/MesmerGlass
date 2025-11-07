"""
Test script to verify spiral rotation_speed accuracy across full range.

Tests rotation speeds from 4.0x (min) to 40.0x (max), including reverse (-).
Measures actual phase increment and compares to expected values.
"""

import sys
import time
import math
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesmerglass.mesmerloom.spiral import SpiralDirector


def measure_rotation_speed(director: SpiralDirector, rotation_speed: float, test_rotations: int = 5) -> dict:
    """
    Measure actual rotation speed by rotating spiral and tracking phase changes.
    
    Args:
        director: SpiralDirector instance
        rotation_speed: Speed to test (e.g., 4.0, 8.0, 20.0, 30.0, -30.0)
        test_rotations: Number of times to call rotate_spiral()
        
    Returns:
        dict with test results
    """
    # Set rotation speed
    director.set_rotation_speed(rotation_speed)
    
    # Reset phase to known state
    director._phase_accumulator = 0.0
    director.state.phase = 0.0
    
    # Standard rotation amount (matching typical visual programs)
    amount = 2.0
    
    # Expected phase increment per rotation
    expected_per_rotation = (amount * (rotation_speed / 4.0)) / (32.0 * math.sqrt(float(director.spiral_width)))
    
    # Track phase changes
    phase_before = director.state.phase
    
    for _ in range(test_rotations):
        director.rotate_spiral(amount)
    
    phase_after = director.state.phase
    
    # Calculate actual increment (preserve sign for negative speeds)
    actual_total_increment = phase_after - phase_before
    
    # Don't wrap negative increments - they should stay negative
    # (Negative rotation_speed causes negative phase increment)
    
    actual_per_rotation = actual_total_increment / test_rotations
    
    # Calculate speed multiplier (relative to 4.0 baseline)
    baseline_per_rotation = (amount * (4.0 / 4.0)) / (32.0 * math.sqrt(float(director.spiral_width)))
    actual_multiplier = actual_per_rotation / baseline_per_rotation if baseline_per_rotation != 0 else 0
    expected_multiplier = rotation_speed / 4.0
    
    # Calculate error
    error_percent = abs(actual_multiplier - expected_multiplier) / abs(expected_multiplier) * 100 if expected_multiplier != 0 else 0
    
    return {
        "rotation_speed": rotation_speed,
        "expected_per_rotation": expected_per_rotation,
        "actual_per_rotation": actual_per_rotation,
        "expected_multiplier": expected_multiplier,
        "actual_multiplier": actual_multiplier,
        "error_percent": error_percent,
        "phase_before": phase_before,
        "phase_after": phase_after,
        "test_rotations": test_rotations,
        "spiral_width": director.spiral_width
    }


def run_speed_tests():
    """Run comprehensive speed tests across full range."""
    print("=" * 80)
    print("SPIRAL ROTATION SPEED ACCURACY TEST")
    print("=" * 80)
    print()
    
    # Create director with standard settings
    director = SpiralDirector()
    director.resolution = (1920, 1080)
    director.spiral_width = 360  # Standard width
    
    print(f"Test Configuration:")
    print(f"  Spiral Width: {director.spiral_width}°")
    print(f"  Rotation Amount: 2.0 (standard)")
    print(f"  Test Rotations: 10 per speed")
    print(f"  Baseline Speed: 4.0x (1.0 multiplier)")
    print()
    
    # Test speeds covering full range
    test_speeds = [
        # Minimum range
        4.0,   # Baseline (1.0x)
        5.0,   # 1.25x
        8.0,   # 2.0x
        
        # Low-medium range
        10.0,  # 2.5x
        12.0,  # 3.0x
        16.0,  # 4.0x
        
        # Medium-high range
        20.0,  # 5.0x
        24.0,  # 6.0x
        30.0,  # 7.5x
        
        # High range
        35.0,  # 8.75x
        40.0,  # 10.0x (maximum)
        
        # Reverse (negative speeds)
        -4.0,  # Baseline reverse
        -8.0,  # 2x reverse
        -16.0, # 4x reverse
        -20.0, # 5x reverse
        -30.0, # 7.5x reverse
        -40.0, # 10x reverse (max)
    ]
    
    print("Testing Speed Range:")
    print(f"  Forward: 4.0x to 40.0x")
    print(f"  Reverse: -4.0x to -40.0x")
    print()
    print("=" * 80)
    print()
    
    results = []
    passed = 0
    failed = 0
    tolerance = 0.1  # Allow 0.1% error tolerance
    
    for speed in test_speeds:
        result = measure_rotation_speed(director, speed, test_rotations=10)
        results.append(result)
        
        status = "✅ PASS" if result["error_percent"] < tolerance else "❌ FAIL"
        if result["error_percent"] < tolerance:
            passed += 1
        else:
            failed += 1
        
        print(f"Speed: {speed:6.1f}x  |  Expected Mult: {result['expected_multiplier']:6.3f}  |  "
              f"Actual Mult: {result['actual_multiplier']:6.3f}  |  "
              f"Error: {result['error_percent']:5.2f}%  |  {status}")
    
    print()
    print("=" * 80)
    print("DETAILED RESULTS")
    print("=" * 80)
    print()
    
    # Print detailed table
    print(f"{'Speed':<8} {'Expected':<12} {'Actual':<12} {'Error':<10} {'Status'}")
    print(f"{'(x)':<8} {'Multiplier':<12} {'Multiplier':<12} {'(%)':<10} {''}")
    print("-" * 80)
    
    for result in results:
        status = "✅ PASS" if result["error_percent"] < tolerance else "❌ FAIL"
        print(f"{result['rotation_speed']:<8.1f} {result['expected_multiplier']:<12.4f} "
              f"{result['actual_multiplier']:<12.4f} {result['error_percent']:<10.2f} {status}")
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print(f"Total Tests: {len(results)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} {'❌' if failed > 0 else ''}")
    print(f"Success Rate: {(passed/len(results)*100):.1f}%")
    print()
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! Rotation speed is accurately applied across full range.")
    else:
        print("⚠️  SOME TESTS FAILED! Check results above.")
        print()
        print("Failed speeds:")
        for result in results:
            if result["error_percent"] >= tolerance:
                print(f"  - {result['rotation_speed']:6.1f}x: "
                      f"expected {result['expected_multiplier']:.4f}, "
                      f"got {result['actual_multiplier']:.4f} "
                      f"({result['error_percent']:.2f}% error)")
    
    print()
    
    # Visual Mode Creator speed range check
    print("=" * 80)
    print("VISUAL MODE CREATOR COMPATIBILITY CHECK")
    print("=" * 80)
    print()
    print("VMC exports rotation_speed in range: 4.0 to 40.0")
    print("(Slider range: 40-400, divided by 10)")
    print()
    
    vmc_speeds = [4.0, 10.0, 20.0, 30.0, 40.0]
    print(f"{'VMC Slider':<12} {'JSON Value':<12} {'Multiplier':<12} {'Status'}")
    print("-" * 80)
    
    for speed in vmc_speeds:
        slider_value = int(speed * 10)
        result = measure_rotation_speed(director, speed, test_rotations=5)
        status = "✅" if result["error_percent"] < tolerance else "❌"
        print(f"{slider_value:<12} {speed:<12.1f} {result['actual_multiplier']:<12.3f} {status}")
    
    print()
    
    return failed == 0


def test_reverse_direction():
    """Test that negative speeds correctly reverse rotation direction."""
    print()
    print("=" * 80)
    print("REVERSE DIRECTION TEST")
    print("=" * 80)
    print()
    
    director = SpiralDirector()
    director.resolution = (1920, 1080)
    director.spiral_width = 360
    
    test_cases = [
        (20.0, "Forward 20x"),
        (-20.0, "Reverse 20x"),
        (30.0, "Forward 30x"),
        (-30.0, "Reverse 30x"),
    ]
    
    print(f"{'Speed':<12} {'Direction':<15} {'Phase Change':<15} {'Sign Check'}")
    print("-" * 80)
    
    all_correct = True
    
    for speed, description in test_cases:
        director.set_rotation_speed(speed)
        director._phase_accumulator = 0.5  # Start at middle
        director.state.phase = 0.5
        
        phase_before = director.state.phase
        director.rotate_spiral(2.0)
        phase_after = director.state.phase
        
        phase_change = phase_after - phase_before
        expected_sign = "+" if speed > 0 else "-"
        actual_sign = "+" if phase_change > 0 else "-"
        
        correct = (expected_sign == actual_sign)
        status = "✅ CORRECT" if correct else "❌ WRONG"
        
        if not correct:
            all_correct = False
        
        print(f"{speed:<12.1f} {description:<15} {phase_change:<+15.6f} {status}")
    
    print()
    if all_correct:
        print("✅ All reverse direction tests passed!")
    else:
        print("❌ Some reverse direction tests failed!")
    
    return all_correct


def test_edge_cases():
    """Test edge cases and boundary conditions."""
    print()
    print("=" * 80)
    print("EDGE CASES TEST")
    print("=" * 80)
    print()
    
    director = SpiralDirector()
    director.resolution = (1920, 1080)
    
    edge_cases = [
        (4.0, 360, "Minimum speed, standard width"),
        (40.0, 360, "Maximum speed, standard width"),
        (20.0, 60, "Medium speed, narrow width"),
        (20.0, 180, "Medium speed, medium width"),
        (-40.0, 360, "Maximum reverse, standard width"),
        (0.0, 360, "Zero speed (should clamp)"),
        (50.0, 360, "Above max (should clamp to 40.0)"),
        (-50.0, 360, "Below min (should clamp to -40.0)"),
    ]
    
    print(f"{'Speed':<10} {'Width':<8} {'Description':<30} {'Status'}")
    print("-" * 80)
    
    all_passed = True
    
    for speed, width, description in edge_cases:
        director.spiral_width = width
        director.set_rotation_speed(speed)
        
        # Check clamping
        clamped_speed = max(-40.0, min(40.0, speed))
        actual_speed = director.rotation_speed
        
        correct = abs(actual_speed - clamped_speed) < 0.001
        status = "✅ PASS" if correct else "❌ FAIL"
        
        if not correct:
            all_passed = False
        
        print(f"{speed:<10.1f} {width:<8} {description:<30} {status}")
        
        if not correct:
            print(f"  Expected: {clamped_speed:.1f}, Got: {actual_speed:.1f}")
    
    print()
    if all_passed:
        print("✅ All edge case tests passed!")
    else:
        print("❌ Some edge case tests failed!")
    
    return all_passed


if __name__ == "__main__":
    print()
    print("🧪 COMPREHENSIVE SPIRAL ROTATION SPEED TEST")
    print()
    
    start_time = time.time()
    
    # Run all tests
    speed_test_passed = run_speed_tests()
    reverse_test_passed = test_reverse_direction()
    edge_test_passed = test_edge_cases()
    
    elapsed = time.time() - start_time
    
    print()
    print("=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    print()
    print(f"Speed Accuracy Tests: {'✅ PASSED' if speed_test_passed else '❌ FAILED'}")
    print(f"Reverse Direction Tests: {'✅ PASSED' if reverse_test_passed else '❌ FAILED'}")
    print(f"Edge Cases Tests: {'✅ PASSED' if edge_test_passed else '❌ FAILED'}")
    print()
    print(f"Total Time: {elapsed:.2f}s")
    print()
    
    if speed_test_passed and reverse_test_passed and edge_test_passed:
        print("🎉 ALL TESTS PASSED! Spiral rotation speed is working correctly.")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED! Review results above.")
        sys.exit(1)
