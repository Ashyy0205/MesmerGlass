"""
Zoom Calibration Tool (CLI-based)

Simple command-line tool to calculate and save zoom rate calibrations
for different spiral types and rotation speeds.

This tool helps you determine the correct zoom_factor for each spiral type
by allowing you to test different rates and record what looks best.

Usage:
    1. Run MesmerGlass in one window
    2. Run this script in another terminal:
       python scripts/calibrate_zoom.py
    3. Input spiral type, rotation speed, and observed zoom rate
    4. Script calculates the zoom factor
    5. Save all calibrations to JSON and generate Python code

Example Session:
    > 3                    # Linear spiral
    > 4.0                  # Normal rotation speed
    > 0.25                 # Observed good zoom rate
    > y                    # Record it
    > save                 # Save to JSON
    > code                 # Generate Python code
"""
import sys
import json
import math
from pathlib import Path
from typing import Dict


class ZoomCalibrator:
    """CLI tool for calibrating zoom rates."""
    
    def __init__(self):
        self.calibration_file = Path("zoom_calibration.json")
        self.calibrations: Dict[int, Dict[str, float]] = {}
        
        # Current default zoom factors (from improved-zoom-system.md)
        self.default_factors = {
            1: 0.5,   # log spiral: gentle pull
            2: 1.0,   # r² (quad): moderate pull
            3: 1.0,   # r (linear): moderate pull - DEFAULT
            4: 1.4,   # √r (sqrt): strong pull (tighter center)
            5: 1.0,   # |r-1| (inverse): moderate pull
            6: 0.33,  # r^6 (power): very gentle pull (extreme curves)
            7: 1.0    # sawtooth/modulated: moderate pull
        }
        
        # Spiral type names
        self.spiral_names = {
            1: "log",
            2: "r² (quad)",
            3: "r (linear)",
            4: "√r (sqrt)",
            5: "|r-1| (inverse)",
            6: "r^6 (power)",
            7: "sawtooth"
        }
        
        self.load_calibration()
    
    def calculate_auto_rate(self, spiral_type: int, rotation_speed: float) -> float:
        """Calculate auto zoom rate using current formula."""
        zoom_factor = self.default_factors.get(spiral_type, 1.0)
        return 0.5 * (rotation_speed / 10.0) * zoom_factor
    
    def calculate_zoom_factor(self, zoom_rate: float, rotation_speed: float) -> float:
        """Calculate zoom factor from observed zoom rate."""
        # zoom_rate = 0.5 * (rotation_speed / 10) * zoom_factor
        # => zoom_factor = zoom_rate / (0.5 * rotation_speed / 10)
        return zoom_rate / (0.5 * rotation_speed / 10.0)
    
    def record_calibration(self, spiral_type: int, rotation_speed: float, zoom_rate: float):
        """Record a calibration."""
        zoom_factor = self.calculate_zoom_factor(zoom_rate, rotation_speed)
        
        if spiral_type not in self.calibrations:
            self.calibrations[spiral_type] = {}
        
        speed_key = f"{rotation_speed:.1f}"
        self.calibrations[spiral_type][speed_key] = {
            "zoom_rate": zoom_rate,
            "zoom_factor": zoom_factor
        }
        
        print(f"\n✅ Recorded:")
        print(f"   Spiral Type {spiral_type} ({self.spiral_names[spiral_type]})")
        print(f"   Rotation Speed: {rotation_speed:.1f}x")
        print(f"   Zoom Rate: {zoom_rate:.3f}")
        print(f"   Zoom Factor: {zoom_factor:.3f}")
    
    def save_calibration(self):
        """Save calibrations to JSON file."""
        if not self.calibrations:
            print("\n⚠️  No calibrations to save")
            return
        
        try:
            with open(self.calibration_file, 'w') as f:
                json.dump(self.calibrations, f, indent=2)
            
            print(f"\n✅ Saved calibration to: {self.calibration_file}")
            print(f"   Total spiral types: {len(self.calibrations)}")
        except Exception as e:
            print(f"\n❌ Failed to save: {e}")
    
    def load_calibration(self):
        """Load existing calibration file."""
        if not self.calibration_file.exists():
            return
        
        try:
            with open(self.calibration_file, 'r') as f:
                data = json.load(f)
                # Convert string keys back to ints
                self.calibrations = {int(k): v for k, v in data.items()}
            print(f"✅ Loaded existing calibration: {len(self.calibrations)} spiral types\n")
        except Exception as e:
            print(f"⚠️  Failed to load calibration: {e}\n")
    
    def print_calibrations(self):
        """Print all recorded calibrations."""
        if not self.calibrations:
            print("\n⚠️  No calibrations recorded yet")
            return
        
        print("\n" + "=" * 70)
        print(" RECORDED CALIBRATIONS")
        print("=" * 70)
        
        for spiral_type in sorted(self.calibrations.keys()):
            print(f"\nSpiral Type {spiral_type}: {self.spiral_names[spiral_type]}")
            print("-" * 70)
            
            speeds = self.calibrations[spiral_type]
            for speed_key in sorted(speeds.keys(), key=lambda x: float(x)):
                data = speeds[speed_key]
                zoom_rate = data["zoom_rate"]
                zoom_factor = data["zoom_factor"]
                
                print(f"  {speed_key:>6}x: rate={zoom_rate:.3f}, factor={zoom_factor:.3f}")
        
        print("=" * 70 + "\n")
    
    def generate_python_code(self):
        """Generate Python code with average zoom factors."""
        if not self.calibrations:
            print("\n⚠️  No calibrations to generate code from")
            return
        
        print("\n" + "=" * 70)
        print(" GENERATED PYTHON CODE")
        print("=" * 70)
        print("\n# Calibrated zoom factors (paste into compositor.py)")
        print("self._zoom_factors = {")
        
        for spiral_type in sorted(self.calibrations.keys()):
            speeds = self.calibrations[spiral_type]
            
            # Calculate average zoom factor across all speeds
            factors = [data["zoom_factor"] for data in speeds.values()]
            avg_factor = sum(factors) / len(factors)
            
            comment = f"# {self.spiral_names[spiral_type]}"
            print(f"    {spiral_type}: {avg_factor:.3f},  {comment}")
        
        print("}")
        print("=" * 70 + "\n")
    
    def interactive_session(self):
        """Run interactive calibration session."""
        print("\n" + "=" * 70)
        print(" ZOOM CALIBRATION TOOL")
        print("=" * 70)
        print("\nInstructions:")
        print("1. Run MesmerGlass in another window")
        print("2. Select spiral type and rotation speed in MesmerGlass UI")
        print("3. Watch how fast the background zooms")
        print("4. Enter the settings here and desired zoom rate")
        print("5. Record multiple calibrations, then save")
        print()
        print("Commands: 'quit', 'save', 'print', 'code'")
        print("=" * 70 + "\n")
        
        while True:
            try:
                # Get spiral type
                print("Enter spiral type (1-7) or command:")
                inp = input("> ").strip().lower()
                
                if inp == 'quit' or inp == 'q' or inp == 'exit':
                    break
                elif inp == 'save' or inp == 's':
                    self.save_calibration()
                    continue
                elif inp == 'print' or inp == 'p':
                    self.print_calibrations()
                    continue
                elif inp == 'code' or inp == 'c':
                    self.generate_python_code()
                    continue
                
                try:
                    spiral_type = int(inp)
                    if spiral_type < 1 or spiral_type > 7:
                        print("❌ Spiral type must be 1-7")
                        continue
                except ValueError:
                    print("❌ Invalid input")
                    continue
                
                # Get rotation speed
                print(f"\nSpiral Type {spiral_type} ({self.spiral_names[spiral_type]})")
                print("Enter rotation speed (4.0-40.0):")
                try:
                    rotation_speed = float(input("> ").strip())
                    if rotation_speed < 4.0 or rotation_speed > 40.0:
                        print("❌ Rotation speed must be 4.0-40.0")
                        continue
                except ValueError:
                    print("❌ Invalid number")
                    continue
                
                # Show auto rate
                auto_rate = self.calculate_auto_rate(spiral_type, rotation_speed)
                print(f"\nAuto zoom rate (current formula): {auto_rate:.3f}")
                
                # Get desired rate
                print("\nEnter desired zoom rate (or 'auto' to keep current):")
                rate_input = input("> ").strip().lower()
                
                if rate_input == 'auto':
                    zoom_rate = auto_rate
                else:
                    try:
                        zoom_rate = float(rate_input)
                        if zoom_rate < 0.001 or zoom_rate > 5.0:
                            print("❌ Zoom rate should be 0.001-5.0")
                            continue
                    except ValueError:
                        print("❌ Invalid number")
                        continue
                
                # Calculate factor and show result
                zoom_factor = self.calculate_zoom_factor(zoom_rate, rotation_speed)
                
                print(f"\n📊 CALCULATION RESULTS:")
                print(f"   Zoom Rate:   {zoom_rate:.3f}")
                print(f"   Zoom Factor: {zoom_factor:.3f}")
                print(f"   Time to 2x:  {math.log(2.0) / zoom_rate:.1f} seconds")
                print(f"   Time to 5x:  {math.log(5.0) / zoom_rate:.1f} seconds")
                
                # Ask to record
                print("\nRecord this calibration? (y/n):")
                if input("> ").strip().lower() == 'y':
                    self.record_calibration(spiral_type, rotation_speed, zoom_rate)
                
                print()
                
            except KeyboardInterrupt:
                print("\n\nExiting...")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
        
        # Final save prompt
        if self.calibrations:
            print("\nSave calibrations before exit? (y/n):")
            if input("> ").strip().lower() == 'y':
                self.save_calibration()
                self.generate_python_code()
        
        print("\n✅ Calibration session complete!\n")


def main():
    calibrator = ZoomCalibrator()
    calibrator.interactive_session()


if __name__ == "__main__":
    main()
