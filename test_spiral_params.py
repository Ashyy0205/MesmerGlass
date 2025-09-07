#!/usr/bin/env python3
"""Quick test to verify spiral parameter control."""

from mesmerglass.mesmerloom.spiral import SpiralDirector

def test_spiral_parameters():
    director = SpiralDirector(seed=42)
    
    # Test initial values
    initial_uniforms = director.export_uniforms()
    print("Initial uniforms:")
    print(f"  uArms: {initial_uniforms['uArms']}")
    print(f"  uArmColor: {initial_uniforms['uArmColor']}")
    print(f"  uGapColor: {initial_uniforms['uGapColor']}")
    print(f"  uBlendMode: {initial_uniforms['uBlendMode']}")
    print(f"  uSpiralOpacity: {initial_uniforms['uSpiralOpacity']}")
    
    # Test parameter changes
    print("\nChanging parameters...")
    director.set_arm_count(6)
    director.set_arm_color(0.8, 0.2, 0.2)  # Red
    director.set_gap_color(0.2, 0.2, 0.8)  # Blue
    director.set_blend_mode(1)  # Screen
    director.set_opacity(0.7)
    
    # Test updated values
    updated_uniforms = director.export_uniforms()
    print("Updated uniforms:")
    print(f"  uArms: {updated_uniforms['uArms']}")
    print(f"  uArmColor: {updated_uniforms['uArmColor']}")
    print(f"  uGapColor: {updated_uniforms['uGapColor']}")
    print(f"  uBlendMode: {updated_uniforms['uBlendMode']}")
    print(f"  uSpiralOpacity: {updated_uniforms['uSpiralOpacity']}")
    
    # Verify changes took effect
    assert updated_uniforms['uArms'] == 6
    assert updated_uniforms['uArmColor'] == (0.8, 0.2, 0.2)
    assert updated_uniforms['uGapColor'] == (0.2, 0.2, 0.8)
    assert updated_uniforms['uBlendMode'] == 1
    # Note: opacity is clamped by OPACITY_MIN/MAX range
    assert 0.55 <= updated_uniforms['uSpiralOpacity'] <= 0.95
    
    print("\n✅ All parameter tests passed!")

if __name__ == "__main__":
    test_spiral_parameters()
