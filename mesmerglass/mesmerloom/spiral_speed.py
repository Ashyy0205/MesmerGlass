"""
Unified Spiral Speed Calculation Module

This module provides consistent spiral speed calculations for both VMC and Launcher.
Converts RPM (rotations per minute) directly to phase increments.

Key insight: rotation_speed should represent actual RPM, not a multiplier.
"""

import math
from typing import Optional


class SpiralSpeedCalculator:
    """Unified spiral speed calculation for consistent rotation across VMC and Launcher"""
    
    @staticmethod
    def rpm_to_phase_per_second(rpm: float) -> float:
        """
        Convert RPM to phase increment per second.
        
        Args:
            rpm: Rotations per minute (e.g., 4.0 = 4 rotations per minute)
            
        Returns:
            Phase increment per second (0.0 to 1.0 = one full rotation)
            
        Example:
            4.0 RPM = 4/60 = 0.0667 rotations/sec = 0.0667 phase/sec
            8.0 RPM = 8/60 = 0.1333 rotations/sec = 0.1333 phase/sec
        """
        return rpm / 60.0
    
    @staticmethod 
    def rpm_to_phase_per_frame(rpm: float, fps: float = 60.0) -> float:
        """
        Convert RPM to phase increment per frame.
        
        Args:
            rpm: Rotations per minute  
            fps: Frames per second (default 60 FPS)
            
        Returns:
            Phase increment per frame
            
        Example:
            4.0 RPM at 60 FPS = (4/60) / 60 = 0.0011 phase/frame
            8.0 RPM at 60 FPS = (8/60) / 60 = 0.0022 phase/frame
        """
        phase_per_second = SpiralSpeedCalculator.rpm_to_phase_per_second(rpm)
        return phase_per_second / fps
    
    @staticmethod
    def rpm_to_degrees_per_second(rpm: float) -> float:
        """
        Convert RPM to degrees per second for validation.
        
        Args:
            rpm: Rotations per minute
            
        Returns:
            Degrees per second
            
        Example:
            4.0 RPM = (4/60) * 360 = 24.0 degrees/second
            8.0 RPM = (8/60) * 360 = 48.0 degrees/second
        """
        rotations_per_second = rpm / 60.0
        return rotations_per_second * 360.0
    
    @staticmethod
    def calculate_spiral_increment(
        rpm: float, 
        spiral_width: int, 
        fps: float = 60.0,
        bypass_legacy_formula: bool = True
    ) -> float:
        """
        Calculate the spiral phase increment for direct use in spiral update.
        
        Args:
            rpm: Target rotations per minute
            spiral_width: Spiral width parameter (affects calculation)
            fps: Frames per second
            bypass_legacy_formula: If True, use direct RPM calculation.
                                  If False, use legacy Trance formula scaling.
                                  
        Returns:
            Phase increment to advance spiral by each frame
        """
        if bypass_legacy_formula:
            # Direct RPM to phase conversion (RECOMMENDED)
            return SpiralSpeedCalculator.rpm_to_phase_per_frame(rpm, fps)
        else:
            # Legacy Trance formula: increment = effective_amount / (32 * sqrt(spiral_width))
            # To achieve RPM, we need: effective_amount = rpm * scaling_factor
            # where scaling_factor makes the math work out to desired RPM
            phase_per_frame = SpiralSpeedCalculator.rpm_to_phase_per_frame(rpm, fps)
            scaling_factor = 32.0 * math.sqrt(float(spiral_width))
            return phase_per_frame * scaling_factor / rpm  # This recovers the "amount" needed
    
    @staticmethod
    def validate_speed_calculation(
        rpm: float,
        measured_phase_per_second: float,
        tolerance: float = 0.1
    ) -> tuple[bool, float, str]:
        """
        Validate that measured phase change matches expected RPM.
        
        Args:
            rpm: Target RPM
            measured_phase_per_second: Measured phase change per second  
            tolerance: Acceptable error percentage (0.1 = 10%)
            
        Returns:
            (is_accurate, accuracy_percentage, status_message)
        """
        expected_phase_per_second = SpiralSpeedCalculator.rpm_to_phase_per_second(rpm)
        
        if expected_phase_per_second == 0:
            return False, 0.0, "Cannot validate zero RPM"
        
        accuracy_percentage = (measured_phase_per_second / expected_phase_per_second) * 100.0
        error_percentage = abs(accuracy_percentage - 100.0) / 100.0
        
        is_accurate = error_percentage <= tolerance
        
        status = f"Target: {rpm:.1f} RPM, Measured: {measured_phase_per_second:.4f} phase/s, Accuracy: {accuracy_percentage:.1f}%"
        
        return is_accurate, accuracy_percentage, status


# Convenience functions for common use cases
def rpm_to_phase_increment(rpm: float, fps: float = 60.0) -> float:
    """Quick conversion: RPM → phase increment per frame"""
    return SpiralSpeedCalculator.rpm_to_phase_per_frame(rpm, fps)

def validate_rpm_measurement(rpm: float, measured_degrees_per_sec: float) -> tuple[bool, float]:
    """Quick validation: Check if measured degrees/sec matches target RPM"""
    expected_degrees_per_sec = SpiralSpeedCalculator.rpm_to_degrees_per_second(rpm)
    measured_phase_per_sec = measured_degrees_per_sec / 360.0
    
    is_accurate, accuracy_pct, _ = SpiralSpeedCalculator.validate_speed_calculation(
        rpm, measured_phase_per_sec
    )
    
    return is_accurate, accuracy_pct


if __name__ == "__main__":
    # Test the speed calculator
    print("🧮 Spiral Speed Calculator Test")
    print("=" * 40)
    
    test_rpms = [4.0, 8.0, 16.0, 24.0]
    
    for rpm in test_rpms:
        phase_per_sec = SpiralSpeedCalculator.rpm_to_phase_per_second(rpm)
        phase_per_frame = SpiralSpeedCalculator.rpm_to_phase_per_frame(rpm, 60.0)
        degrees_per_sec = SpiralSpeedCalculator.rpm_to_degrees_per_second(rpm)
        
        print(f"RPM {rpm:5.1f}: {phase_per_sec:.6f} phase/s, {phase_per_frame:.6f} phase/frame, {degrees_per_sec:.1f}°/s")
    
    print("\n✅ Expected results for accurate measurement:")
    print("   4.0 RPM should measure  24.0°/s")
    print("   8.0 RPM should measure  48.0°/s") 
    print("  16.0 RPM should measure  96.0°/s")
    print("  24.0 RPM should measure 144.0°/s")