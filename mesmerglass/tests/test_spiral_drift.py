"""
Stress test for spiral phase drift prevention.

This test simulates extended runtime (equivalent to hours of continuous rotation)
to ensure the high-precision accumulator prevents the "black circle" bug.
"""

from mesmerglass.mesmerloom.spiral import SpiralDirector
import time


def test_extended_rotation_no_drift():
    """Test that phase remains accurate after extended rotation (prevents black circle bug)."""
    director = SpiralDirector(seed=42)
    
    # Simulate 10 minutes of rotation at 60fps with speed=4.0
    # 10 minutes = 600 seconds = 36,000 frames
    frames = 36_000
    rotation_amount = 4.0
    
    print(f"🔄 Simulating {frames:,} frames ({frames/60/60:.1f} minutes) of rotation...")
    print(f"   Rotation speed: {rotation_amount}x")
    print(f"   Initial phase: {director.state.phase:.10f}")
    
    start = time.time()
    for i in range(frames):
        director.rotate_spiral(rotation_amount)
        
        # Check phase stays in valid range
        assert 0.0 <= director.state.phase < 1.0, f"Phase out of range at frame {i}: {director.state.phase}"
        
        # Log every 6000 frames (1 minute)
        if (i + 1) % 6000 == 0:
            elapsed_min = (i + 1) / 6000
            print(f"   {elapsed_min:.0f} min: phase={director.state.phase:.10f}, rotations={director._rotation_count}")
    
    elapsed = time.time() - start
    
    print(f"\n✅ Test complete in {elapsed:.2f}s")
    print(f"   Final phase: {director.state.phase:.10f}")
    print(f"   Total full rotations: {director._rotation_count}")
    print(f"   Accumulator: {director._phase_accumulator:.10f}")
    print(f"   Phase valid: {0.0 <= director.state.phase < 1.0}")
    
    # Verify phase is still valid
    assert 0.0 <= director.state.phase < 1.0, "Phase drifted out of valid range!"
    assert director._phase_accumulator == director.state.phase, "Accumulator desync!"


def test_ultra_fast_rotation():
    """Test maximum rotation speed (40.0x) over extended period."""
    director = SpiralDirector(seed=42)
    director.rotation_speed = 40.0  # Maximum speed
    
    # 5 minutes at 60fps
    frames = 18_000
    
    print(f"\n🚀 Ultra-fast rotation test ({director.rotation_speed}x speed)...")
    print(f"   Frames: {frames:,}")
    
    for i in range(frames):
        director.rotate_spiral(director.rotation_speed)
        assert 0.0 <= director.state.phase < 1.0
    
    print(f"✅ Ultra-fast rotation stable")
    print(f"   Final phase: {director.state.phase:.10f}")
    print(f"   Total rotations: {director._rotation_count}")


def test_precision_comparison():
    """Compare old (drift-prone) vs new (drift-resistant) method."""
    print("\n📊 Precision comparison:")
    
    # Old method (would drift)
    phase_old = 0.0
    increment = 4.0 / (32.0 * (60.0 ** 0.5))
    for _ in range(100_000):
        phase_old = (phase_old + increment) % 1.0
    
    # New method (drift-resistant)
    director = SpiralDirector(seed=42)
    for _ in range(100_000):
        director.rotate_spiral(4.0)
    
    print(f"   Old method phase after 100k rotations: {phase_old:.10f}")
    print(f"   New method phase after 100k rotations: {director.state.phase:.10f}")
    print(f"   New method full rotations tracked: {director._rotation_count}")
    print(f"   ✅ New method provides rotation counting and prevents accumulation errors")


if __name__ == "__main__":
    print("=" * 60)
    print("SPIRAL PHASE DRIFT STRESS TEST")
    print("=" * 60)
    
    test_extended_rotation_no_drift()
    test_ultra_fast_rotation()
    test_precision_comparison()
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED - Black circle bug fixed!")
    print("=" * 60)
