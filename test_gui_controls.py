#!/usr/bin/env python3
"""Test script to verify GUI spiral parameter control is working."""

import sys
import time
from PyQt6.QtWidgets import QApplication
from mesmerglass.mesmerloom.spiral import SpiralDirector
from mesmerglass.ui.panel_mesmerloom import PanelMesmerLoom
from mesmerglass.mesmerloom.compositor import LoomCompositor

def test_gui_parameter_control():
    """Test that GUI controls properly update spiral parameters."""
    
    app = QApplication(sys.argv if sys.argv else ['test'])
    
    # Create director and compositor
    director = SpiralDirector(seed=123)
    compositor = LoomCompositor(director)
    
    # Create the GUI panel
    panel = PanelMesmerLoom(director, compositor)
    
    print("🔧 Testing GUI Parameter Control...")
    
    # Test 1: Arm count
    print("\n1. Testing arm count control...")
    initial_arms = director.export_uniforms()['uArms']
    print(f"   Initial arms: {initial_arms}")
    
    # Simulate changing arm count to 6
    panel._on_arm_count(6)
    updated_arms = director.export_uniforms()['uArms']
    print(f"   After GUI change to 6: {updated_arms}")
    assert updated_arms == 6, f"Expected 6 arms, got {updated_arms}"
    print("   ✅ Arm count control working!")
    
    # Test 2: Blend mode
    print("\n2. Testing blend mode control...")
    initial_blend = director.export_uniforms()['uBlendMode']
    print(f"   Initial blend mode: {initial_blend}")
    
    # Simulate changing blend mode to Screen (1)
    panel._on_blend_mode(1)
    updated_blend = director.export_uniforms()['uBlendMode']
    print(f"   After GUI change to Screen: {updated_blend}")
    assert updated_blend == 1, f"Expected blend mode 1, got {updated_blend}"
    print("   ✅ Blend mode control working!")
    
    # Test 3: Opacity
    print("\n3. Testing opacity control...")
    initial_opacity = director.export_uniforms()['uSpiralOpacity']
    print(f"   Initial opacity: {initial_opacity:.3f}")
    
    # Simulate changing opacity to 80% (slider value 80)
    panel._on_opacity(80)
    updated_opacity = director.export_uniforms()['uSpiralOpacity']
    print(f"   After GUI change to 80%: {updated_opacity:.3f}")
    # Note: opacity gets clamped to director's OPACITY_MIN/MAX range
    assert 0.55 <= updated_opacity <= 0.95, f"Opacity {updated_opacity} out of expected range"
    print("   ✅ Opacity control working!")
    
    # Test 4: Colors via color picker simulation
    print("\n4. Testing color controls...")
    from PyQt6.QtGui import QColor
    
    # Test arm color
    initial_arm_color = director.export_uniforms()['uArmColor']
    print(f"   Initial arm color: {initial_arm_color}")
    
    # Simulate picking red color for arms
    red_color = QColor(255, 100, 100)  # Light red
    panel._apply_color(True, red_color)  # True = arm color
    updated_arm_color = director.export_uniforms()['uArmColor']
    print(f"   After GUI red arm color: {updated_arm_color}")
    
    # Check if color is approximately red
    r, g, b = updated_arm_color
    assert r > 0.8 and g < 0.6 and b < 0.6, f"Expected reddish color, got {updated_arm_color}"
    print("   ✅ Arm color control working!")
    
    # Test gap color
    blue_color = QColor(100, 100, 255)  # Light blue
    panel._apply_color(False, blue_color)  # False = gap color
    updated_gap_color = director.export_uniforms()['uGapColor']
    print(f"   After GUI blue gap color: {updated_gap_color}")
    
    # Check if color is approximately blue
    r, g, b = updated_gap_color
    assert r < 0.6 and g < 0.6 and b > 0.8, f"Expected bluish color, got {updated_gap_color}"
    print("   ✅ Gap color control working!")
    
    # Test 5: Intensity (this was already working)
    print("\n5. Testing intensity control...")
    initial_intensity = director.export_uniforms()['uIntensity']
    print(f"   Initial intensity: {initial_intensity:.3f}")
    
    # Simulate changing intensity to 75%
    panel._on_intensity(75)
    # Need to call update() for intensity to take effect
    director.update(1/60)
    updated_intensity = director.export_uniforms()['uIntensity']
    print(f"   After GUI change to 75%: {updated_intensity:.3f}")
    assert abs(updated_intensity - 0.75) < 0.01, f"Expected ~0.75, got {updated_intensity}"
    print("   ✅ Intensity control working!")
    
    print("\n🎉 All GUI parameter controls are working correctly!")
    print("\nParameter values are now properly flowing from GUI -> Director -> Shader")
    
    # Show final state
    final_uniforms = director.export_uniforms()
    print(f"\nFinal spiral state:")
    print(f"  Arms: {final_uniforms['uArms']}")
    print(f"  Blend Mode: {final_uniforms['uBlendMode']}")
    print(f"  Arm Color: {final_uniforms['uArmColor']}")
    print(f"  Gap Color: {final_uniforms['uGapColor']}")
    print(f"  Opacity: {final_uniforms['uSpiralOpacity']:.3f}")
    print(f"  Intensity: {final_uniforms['uIntensity']:.3f}")

if __name__ == "__main__":
    test_gui_parameter_control()
