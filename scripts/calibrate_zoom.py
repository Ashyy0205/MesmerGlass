"""Live Zoom Calibration Tool

Visual tool for calibrating zoom rate formula to match spiral motion.

Shows spiral + background with live zoom adjustment. You tweak the zoom rate
until it visually matches the spiral's perceived inward pull, then the tool
calculates the optimal formula multiplier.

Usage:
    python scripts/calibrate_zoom.py

Controls:
    - Spiral Type slider: Change spiral type (1-7)
    - Rotation Speed slider: Change rotation speed (4-40)
    - Zoom Rate slider: Manually adjust zoom rate in real-time
    - Calculate Formula button: Show optimal multiplier for formula
    - Reset button: Reset to default formula values
    - Save to Code button: Show updated code snippet
"""
import sys
import math
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QSlider, QPushButton, QTextEdit)
from PyQt6.QtCore import Qt, QTimer

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mesmerglass.mesmerloom.compositor import LoomCompositor
from mesmerglass.mesmerloom.spiral import SpiralDirector
from mesmerglass.content import media
from mesmerglass.content.texture import upload_image_to_gpu


class ZoomCalibrationWindow(QMainWindow):
    """Live zoom calibration tool with spiral preview."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zoom Rate Calibration Tool - 16:9 View")
        self.setGeometry(100, 100, 1700, 900)  # Wider to accommodate 16:9 viewport
        
        # Create spiral director
        self.director = SpiralDirector()
        self.director.set_intensity(0.8)  # Make spiral visible
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # Left side: Spiral compositor (16:9 aspect ratio for accurate testing)
        self.compositor = LoomCompositor(
            director=self.director,
            parent=self,
            trace=False,
            sim_flag=False,
            force_flag=False
        )
        # 16:9 aspect ratio: 1920x1080 scaled down to fit
        self.compositor.setMinimumSize(1280, 720)
        self.compositor.setMaximumHeight(720)  # Maintain aspect ratio
        
        # CRITICAL: Activate the compositor so it actually renders
        self.compositor.set_active(True)
        
        main_layout.addWidget(self.compositor, stretch=2)
        
        # Right side: Controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        main_layout.addWidget(controls_widget, stretch=1)
        
        # Title
        title = QLabel("Zoom Calibration Tool")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        controls_layout.addWidget(title)
        
        # Instructions
        instructions = QLabel(
            "Adjust zoom rate until background motion\n"
            "matches spiral's perceived inward pull.\n\n"
            "Then click 'Calculate Formula' to see\n"
            "the optimal multiplier for the formula."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #666; margin-bottom: 10px;")
        controls_layout.addWidget(instructions)
        
        # Spiral Type slider
        controls_layout.addWidget(QLabel("Spiral Type:"))
        self.spiral_type_slider = QSlider(Qt.Orientation.Horizontal)
        self.spiral_type_slider.setRange(1, 7)
        self.spiral_type_slider.setValue(3)
        self.spiral_type_slider.valueChanged.connect(self.on_spiral_type_changed)
        self.spiral_type_label = QLabel("3 (Linear)")
        controls_layout.addWidget(self.spiral_type_slider)
        controls_layout.addWidget(self.spiral_type_label)
        
        # Rotation Speed slider
        controls_layout.addWidget(QLabel("\nRotation Speed:"))
        self.rotation_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.rotation_speed_slider.setRange(40, 400)  # 4.0 to 40.0 (x10)
        self.rotation_speed_slider.setValue(40)  # 4.0
        self.rotation_speed_slider.valueChanged.connect(self.on_rotation_speed_changed)
        self.rotation_speed_label = QLabel("4.0x")
        controls_layout.addWidget(self.rotation_speed_slider)
        controls_layout.addWidget(self.rotation_speed_label)
        
        # Zoom Rate slider (manual control)
        controls_layout.addWidget(QLabel("\nZoom Rate (Manual):"))
        self.zoom_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_rate_slider.setRange(0, 500)  # 0.0 to 5.0 (x100)
        self.zoom_rate_slider.setValue(20)  # 0.2
        self.zoom_rate_slider.valueChanged.connect(self.on_zoom_rate_changed)
        self.zoom_rate_label = QLabel("0.200")
        controls_layout.addWidget(self.zoom_rate_slider)
        controls_layout.addWidget(self.zoom_rate_label)
        
        # Spiral Opacity slider
        controls_layout.addWidget(QLabel("\nSpiral Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)  # 0% to 100%
        self.opacity_slider.setValue(80)  # 80% default
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        self.opacity_label = QLabel("80%")
        controls_layout.addWidget(self.opacity_slider)
        controls_layout.addWidget(self.opacity_label)
        
        # Current formula display
        controls_layout.addWidget(QLabel("\nCurrent Formula:"))
        self.formula_display = QLabel("rate = 0.5 × (speed/10) × factor")
        self.formula_display.setStyleSheet("background: #f0f0f0; padding: 5px; font-family: monospace;")
        controls_layout.addWidget(self.formula_display)
        
        # Calculated values display
        self.calc_display = QTextEdit()
        self.calc_display.setReadOnly(True)
        self.calc_display.setMaximumHeight(150)
        self.calc_display.setStyleSheet("background: #f9f9f9; font-family: monospace; font-size: 10px;")
        controls_layout.addWidget(self.calc_display)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.calc_button = QPushButton("Calculate Formula")
        self.calc_button.clicked.connect(self.calculate_optimal_multiplier)
        button_layout.addWidget(self.calc_button)
        
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(self.reset_button)
        
        controls_layout.addLayout(button_layout)
        
        self.save_button = QPushButton("Export Calibration Data")
        self.save_button.clicked.connect(self.save_calibration_data)
        self.save_button.setEnabled(False)
        self.save_button.setStyleSheet("background: #4CAF50; color: white; font-weight: bold;")
        controls_layout.addWidget(self.save_button)
        
        controls_layout.addStretch()
        
        # Data collection for calibration
        self.calibration_data = []  # List of (spiral_type, rotation_speed, manual_zoom_rate)
        
        # Start animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_spiral)
        self.timer.start(16)  # ~60 FPS
        
        # Force compositor to start rendering
        self.render_timer = QTimer()
        self.render_timer.timeout.connect(lambda: self.compositor.update())
        self.render_timer.start(16)  # ~60 FPS
        
        # Load test image after compositor is initialized (delayed)
        QTimer.singleShot(500, self.load_test_image)
        
        # Track manual zoom override
        self.manual_zoom_rate = None  # None = use auto-calculated, float = use manual
        
        # Update initial state
        self.on_spiral_type_changed(3)
        self.on_rotation_speed_changed(40)
        self.on_zoom_rate_changed(20)
    
    def load_test_image(self):
        """Load test images and start cycling through them."""
        import logging
        
        # Find all images in MEDIA/Images
        media_dir = Path(__file__).parent.parent / "MEDIA" / "Images"
        self.image_files = list(media_dir.glob("*.jpg")) + list(media_dir.glob("*.png"))
        self.image_files.sort()  # Consistent order
        self.current_image_index = 0
        
        if self.image_files:
            self.load_next_image()
            
            # Start image cycling timer (change every 48 frames = ~0.8 seconds like practice)
            self.image_cycle_timer = QTimer()
            self.image_cycle_timer.timeout.connect(self.cycle_image)
            self.image_cycle_timer.start(int(48 * (1000/60)))  # 48 frames at 60fps
            
            logging.info(f"[calibration] Found {len(self.image_files)} images, starting cycle")
    
    def load_next_image(self):
        """Load the next image in the cycle."""
        import logging
        
        if not self.image_files:
            return
        
        try:
            # Load image
            image_file = self.image_files[self.current_image_index]
            image_data = media.load_image_sync(image_file)
            
            # Upload to GPU
            self.compositor.makeCurrent()
            texture_id = upload_image_to_gpu(image_data)
            
            # Set as background with exponential zoom
            self.compositor.set_background_texture(
                texture_id,
                zoom=1.0,
                image_width=image_data.width,
                image_height=image_data.height
            )
            
            # Start zoom animation in exponential mode
            self.compositor.start_zoom_animation(
                start_zoom=1.0,
                duration_frames=9999,  # Never stop
                mode="exponential"
            )
            
            # Apply manual zoom rate override if set
            if self.manual_zoom_rate is not None:
                import time
                self.compositor._zoom_rate = self.manual_zoom_rate
                self.compositor._zoom_start_time = time.time()
                self.compositor._zoom_current = 1.0
            
            logging.info(f"[calibration] Loaded image {self.current_image_index + 1}/{len(self.image_files)}: {image_file.name}")
        except Exception as e:
            logging.error(f"[calibration] Failed to load image: {e}")
            import traceback
            traceback.print_exc()
    
    def cycle_image(self):
        """Cycle to the next image."""
        if not self.image_files:
            return
        
        self.current_image_index = (self.current_image_index + 1) % len(self.image_files)
        self.load_next_image()
    
    def update_spiral(self):
        """Update spiral animation."""
        self.director.update(1/60.0)
        self.compositor.update_zoom_animation()
        self.compositor.update()  # Trigger repaint
    
    def on_spiral_type_changed(self, value):
        """Handle spiral type slider change."""
        type_names = {
            1: "Log",
            2: "Quad (r²)",
            3: "Linear (r)",
            4: "Sqrt (√r)",
            5: "Inverse",
            6: "Power (r⁶)",
            7: "Sawtooth"
        }
        self.director.set_spiral_type(value)
        self.spiral_type_label.setText(f"{value} ({type_names.get(value, 'Unknown')})")
        self.update_formula_display()
    
    def on_rotation_speed_changed(self, value):
        """Handle rotation speed slider change."""
        speed = value / 10.0
        self.director.set_rotation_speed(speed)
        self.rotation_speed_label.setText(f"{speed:.1f}x")
        self.update_formula_display()
    
    def on_zoom_rate_changed(self, value):
        """Handle manual zoom rate slider change."""
        import time
        rate = value / 100.0
        self.zoom_rate_label.setText(f"{rate:.3f}")
        
        # Store manual zoom rate for persistence across image changes
        self.manual_zoom_rate = rate
        
        # Override compositor zoom rate
        self.compositor._zoom_rate = rate
        self.compositor._zoom_start_time = time.time()
        self.compositor._zoom_current = 1.0
        
        self.update_formula_display()
    
    def on_opacity_changed(self, value):
        """Handle spiral opacity slider change."""
        opacity = value / 100.0
        self.opacity_label.setText(f"{value}%")
        
        # Update director intensity (opacity)
        self.director.set_intensity(opacity)
    
    def update_formula_display(self):
        """Update formula display with current values."""
        spiral_type = self.spiral_type_slider.value()
        rotation_speed = self.rotation_speed_slider.value() / 10.0
        manual_rate = self.zoom_rate_slider.value() / 100.0
        
        # Get expected rate from default formula
        default_factors = {1: 0.5, 2: 1.0, 3: 1.0, 4: 1.4, 5: 1.0, 6: 0.33, 7: 1.0}
        factor = default_factors.get(spiral_type, 1.0)
        expected_rate = 0.5 * (rotation_speed / 10.0) * factor
        
        self.formula_display.setText(
            f"Type={spiral_type}, Speed={rotation_speed:.1f}x\n"
            f"Expected: {expected_rate:.3f}\n"
            f"Manual: {manual_rate:.3f}"
        )
    
    def calculate_optimal_multiplier(self):
        """Calculate optimal formula multiplier from manual adjustments."""
        spiral_type = self.spiral_type_slider.value()
        rotation_speed = self.rotation_speed_slider.value() / 10.0
        manual_rate = self.zoom_rate_slider.value() / 100.0
        
        # Record this calibration point
        self.calibration_data.append((spiral_type, rotation_speed, manual_rate))
        
        # Calculate what multiplier would give this rate
        # Formula: manual_rate = multiplier * (rotation_speed / 10.0) * factor
        default_factors = {1: 0.5, 2: 1.0, 3: 1.0, 4: 1.4, 5: 1.0, 6: 0.33, 7: 1.0}
        factor = default_factors.get(spiral_type, 1.0)
        
        # Solve for multiplier: multiplier = manual_rate / ((rotation_speed / 10.0) * factor)
        base = (rotation_speed / 10.0) * factor
        if base > 0:
            implied_multiplier = manual_rate / base
        else:
            implied_multiplier = 0.0
        
        # Show results
        result = (
            f"=== Calibration Point {len(self.calibration_data)} ===\n"
            f"Spiral Type: {spiral_type}\n"
            f"Rotation Speed: {rotation_speed:.1f}x\n"
            f"Manual Zoom Rate: {manual_rate:.3f}\n\n"
            f"Implied Multiplier: {implied_multiplier:.3f}\n"
            f"(was 0.5 in original formula)\n\n"
            f"New formula would be:\n"
            f"rate = {implied_multiplier:.3f} × (speed/10) × factor\n"
        )
        
        self.calc_display.setPlainText(result)
        
        # Enable save button if we have data
        if len(self.calibration_data) >= 3:
            self.save_button.setEnabled(True)
    
    def reset_to_defaults(self):
        """Reset to default formula values."""
        self.spiral_type_slider.setValue(3)
        self.rotation_speed_slider.setValue(40)
        
        # Calculate default rate
        default_rate = 0.5 * (4.0 / 10.0) * 1.0  # = 0.2
        self.zoom_rate_slider.setValue(int(default_rate * 100))
        
        self.calc_display.clear()
    
    def save_calibration_data(self):
        """Save calibration data to text file."""
        if len(self.calibration_data) < 1:
            self.calc_display.setPlainText("No calibration data to save!")
            return
        
        from datetime import datetime
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"zoom_calibration_{timestamp}.txt"
        filepath = Path(__file__).parent.parent / filename
        
        # Write data
        with open(filepath, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("ZOOM CALIBRATION DATA\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            
            f.write("CALIBRATION POINTS:\n")
            f.write("-" * 60 + "\n")
            f.write(f"{'#':<4} {'Type':<8} {'Speed':<8} {'Rate':<10} {'Multiplier':<12}\n")
            f.write("-" * 60 + "\n")
            
            default_factors = {1: 0.5, 2: 1.0, 3: 1.0, 4: 1.4, 5: 1.0, 6: 0.33, 7: 1.0}
            
            for i, (spiral_type, rotation_speed, manual_rate) in enumerate(self.calibration_data, 1):
                factor = default_factors.get(spiral_type, 1.0)
                base = (rotation_speed / 10.0) * factor
                multiplier = manual_rate / base if base > 0 else 0.0
                
                type_names = {1: "Log", 2: "Quad", 3: "Linear", 4: "Sqrt", 5: "Inv", 6: "Power", 7: "Saw"}
                type_name = type_names.get(spiral_type, str(spiral_type))
                
                f.write(f"{i:<4} {type_name:<8} {rotation_speed:>6.1f}x  {manual_rate:>8.3f}    {multiplier:>10.3f}\n")
            
            f.write("\n" + "=" * 60 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 60 + "\n\n")
            
            # Calculate statistics
            multipliers = []
            for spiral_type, rotation_speed, manual_rate in self.calibration_data:
                factor = default_factors.get(spiral_type, 1.0)
                base = (rotation_speed / 10.0) * factor
                if base > 0:
                    multipliers.append(manual_rate / base)
            
            if multipliers:
                avg = sum(multipliers) / len(multipliers)
                variance = sum((m - avg) ** 2 for m in multipliers) / len(multipliers)
                std_dev = math.sqrt(variance)
                min_mult = min(multipliers)
                max_mult = max(multipliers)
                
                f.write(f"Total Points: {len(self.calibration_data)}\n")
                f.write(f"Average Multiplier: {avg:.4f}\n")
                f.write(f"Std Deviation: {std_dev:.4f}\n")
                f.write(f"Range: {min_mult:.4f} to {max_mult:.4f}\n\n")
                
                f.write(f"Max Zoom: 5.0x (hardcoded)\n\n")
                
                f.write("CURRENT FORMULA:\n")
                f.write("  zoom_rate = 0.5 * (rotation_speed / 10.0) * zoom_factor\n\n")
                
                f.write("SUGGESTED FORMULA:\n")
                f.write(f"  zoom_rate = {avg:.4f} * (rotation_speed / 10.0) * zoom_factor\n\n")
                
                f.write("USAGE:\n")
                f.write("  Use this data to adjust the multiplier (currently 0.5)\n")
                f.write("  in compositor.py start_zoom_animation() method.\n")
        
        # Show confirmation
        result = (
            f"✅ CALIBRATION DATA SAVED\n\n"
            f"File: {filename}\n"
            f"Location: {filepath}\n\n"
            f"Points saved: {len(self.calibration_data)}\n\n"
            f"You can now use this data to improve\n"
            f"the zoom formula in compositor.py"
        )
        
        self.calc_display.setPlainText(result)


def main():
    """Run calibration tool."""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    app = QApplication(sys.argv)
    window = ZoomCalibrationWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
