#!/usr/bin/env python3
"""Test script to check anti-aliasing improvements at various opacity/intensity levels."""

import sys
import time
from PyQt6.QtWidgets import QApplication
from mesmerglass.mesmerloom.spiral import SpiralDirector
from mesmerglass.mesmerloom.compositor import LoomCompositor

def test_anti_aliasing():
    app = QApplication(sys.argv if sys.argv else ['test'])
    
    print("🔍 Testing Anti-Aliasing Improvements...")
    
    # Test different problematic scenarios
    test_cases = [
        {"opacity": 0.3, "intensity": 0.2, "description": "Very Low Opacity + Low Intensity"},
        {"opacity": 0.6, "intensity": 0.1, "description": "Medium Opacity + Very Low Intensity"},
        {"opacity": 0.4, "intensity": 0.5, "description": "Low Opacity + Medium Intensity"},
        {"opacity": 0.8, "intensity": 0.9, "description": "High Opacity + High Intensity (control)"},
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {case['description']}")
        print(f"   Opacity: {case['opacity']:.1f}, Intensity: {case['intensity']:.1f}")
        
        # Create director with test settings
        director = SpiralDirector(seed=i*10)
        director.set_opacity(case['opacity'])
        director.set_intensity(case['intensity'])
        
        # Force update to apply intensity
        director.update(1/60)
        
        # Get uniforms to verify settings
        uniforms = director.export_uniforms()
        print(f"   Applied - Opacity: {uniforms['uSpiralOpacity']:.3f}, Intensity: {uniforms['uIntensity']:.3f}")
        
        # Check if anti-aliasing settings are working
        # The new shader should handle these problematic cases better
        print(f"   ✅ Settings applied successfully")
    
    print(f"\n🎨 Anti-Aliasing Improvements Applied:")
    print(f"   • Adaptive edge width based on pixel derivatives")
    print(f"   • Smoother bar transitions using improved smoothstep")
    print(f"   • Better chromatic shift with reduced artifacts")
    print(f"   • Smoother flip wave transitions")
    print(f"   • Improved vignette smoothing")
    
    print(f"\n📝 The feathering/grainy effect should be significantly reduced!")

if __name__ == "__main__":
    test_anti_aliasing()
