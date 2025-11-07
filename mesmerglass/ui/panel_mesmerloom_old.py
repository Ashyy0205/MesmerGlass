"""MesmerLoom control panel (Step 3 implementation)."""
from __future__ import annotations
from typing import Tuple
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSlider, QComboBox,
    QPushButton, QSpinBox, QDoubleSpinBox, QGroupBox
)
from PyQt6.QtGui import QColor

def _row(label: str, w: QWidget) -> QWidget:
    box = QWidget(); lay = QHBoxLayout(box); lay.setContentsMargins(4,2,4,2); lay.setSpacing(8)
    lab = QLabel(label); lab.setMinimumWidth(140)
    lay.addWidget(lab,0); lay.addWidget(w,1)
    return box

class PanelMesmerLoom(QWidget):
    intensityChanged = pyqtSignal(float)
    blendModeChanged = pyqtSignal(int)
    armColorChanged = pyqtSignal(tuple)
    gapColorChanged = pyqtSignal(tuple)
    rotationSpeedChanged = pyqtSignal(float)  # 4.0 to 40.0x speed
    zoomSpeedChanged = pyqtSignal(float)  # 0.01 to 0.5 per frame
    mediaModeChanged = pyqtSignal(int)  # 0=images&videos, 1=images only, 2=video focus
    imageDurationChanged = pyqtSignal(int)  # Duration in seconds (1-60)
    videoDurationChanged = pyqtSignal(int)  # Duration in seconds (5-300)

    def __init__(self, director, compositor, parent=None):
        super().__init__(parent)
        self.director = director; self.compositor = compositor
        self._arm_rgba = (1.0,1.0,1.0,1.0); self._gap_rgba = (0.0,0.0,0.0,1.0)  # Black gap (transparent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(10)
        
        # General Controls
        box_gen = QGroupBox("General"); lg = QVBoxLayout(box_gen); lg.setContentsMargins(8,8,8,8); lg.setSpacing(4)
        
        # Media mode selection
        self.cmb_media_mode = QComboBox()
        self.cmb_media_mode.addItems([
            "Images & Videos",
            "Images Only",
            "Video Focus (Not Ready)"
        ])
        self.cmb_media_mode.setCurrentIndex(1)  # Default to Images Only (working mode)
        self.cmb_media_mode.currentIndexChanged.connect(self._on_media_mode)
        lg.addWidget(_row("Media Mode", self.cmb_media_mode))
        
        self.sld_intensity = QSlider(Qt.Orientation.Horizontal); self.sld_intensity.setRange(0,100); lg.addWidget(_row("Opacity", self.sld_intensity))
        self.sld_intensity.valueChanged.connect(self._on_intensity)
        
        self.cmb_blend = QComboBox(); self.cmb_blend.addItems(["Multiply","Screen","SoftLight"]); self.cmb_blend.currentIndexChanged.connect(self._on_blend_mode)
        lg.addWidget(_row("Blend Mode", self.cmb_blend))
        
        # Trance spiral type and width
        self.cmb_spiral_type = QComboBox()
        self.cmb_spiral_type.addItems([
            "1: Logarithmic",
            "2: Quadratic", 
            "3: Linear (Default)",
            "4: Square Root",
            "5: Inverse Spike",
            "6: Power",
            "7: Modulated"
        ])
        self.cmb_spiral_type.setCurrentIndex(2)  # Default to Linear (type 3)
        self.cmb_spiral_type.currentIndexChanged.connect(self._on_spiral_type)
        lg.addWidget(_row("Spiral Type", self.cmb_spiral_type))
        
        self.cmb_spiral_width = QComboBox()
        self.cmb_spiral_width.addItems([
            "60° (6 arms)",
            "72° (5 arms)",
            "90° (4 arms)",
            "120° (3 arms)",
            "180° (2 arms)",
            "360° (1 arm)"
        ])
        self.cmb_spiral_width.setCurrentIndex(0)  # Default to 60°
        self.cmb_spiral_width.currentIndexChanged.connect(self._on_spiral_width)
        lg.addWidget(_row("Spiral Width", self.cmb_spiral_width))
        
        # Rotation speed control
        self.sld_rotation_speed = QSlider(Qt.Orientation.Horizontal)
        self.sld_rotation_speed.setRange(400, 4000)  # 4.0x to 40.0x speed
        self.sld_rotation_speed.setValue(400)  # Default 4.0x (normal speed)
        self.sld_rotation_speed.valueChanged.connect(self._on_rotation_speed)
        lg.addWidget(_row("Rotation Speed", self.sld_rotation_speed))
        
        # Max zoom control
        self.sld_max_zoom = QSlider(Qt.Orientation.Horizontal)
        self.sld_max_zoom.setRange(100, 300)  # 1.0x to 3.0x zoom
        self.sld_max_zoom.setValue(150)  # Default 1.5x zoom
        self.sld_max_zoom.valueChanged.connect(self._on_max_zoom)
        lg.addWidget(_row("Max Zoom", self.sld_max_zoom))
        
        # Image duration control
        self.spin_image_duration = QSpinBox()
        self.spin_image_duration.setRange(1, 60)  # 1-60 seconds
        self.spin_image_duration.setValue(5)  # Default 5 seconds
        self.spin_image_duration.setSuffix(" sec")
        self.spin_image_duration.valueChanged.connect(self._on_image_duration)
        lg.addWidget(_row("Image Duration", self.spin_image_duration))
        
        # Video duration control
        self.spin_video_duration = QSpinBox()
        self.spin_video_duration.setRange(5, 300)  # 5-300 seconds (5min max)
        self.spin_video_duration.setValue(30)  # Default 30 seconds
        self.spin_video_duration.setSuffix(" sec")
        self.spin_video_duration.valueChanged.connect(self._on_video_duration)
        lg.addWidget(_row("Video Duration", self.spin_video_duration))
        
        root.addWidget(box_gen)
        
        # Color Controls
        box_col = QGroupBox("Colors"); lc = QVBoxLayout(box_col); lc.setContentsMargins(8,8,8,8); lc.setSpacing(4)
        self.btn_arm_col = QPushButton("Arm Color"); self.btn_gap_col = QPushButton("Gap Color")
        self.btn_arm_col.clicked.connect(lambda: self._pick_color(True)); self.btn_gap_col.clicked.connect(lambda: self._pick_color(False))
        lc.addWidget(self.btn_arm_col); lc.addWidget(self.btn_gap_col)
        root.addWidget(box_col)
        
        root.addStretch(1)

    # Helpers
    @staticmethod
    def _slider01(v: int) -> float: return max(0.0, min(1.0, v/100.0))

    # Slots
    def _on_intensity(self, v: int):
        f = self._slider01(v); self.intensityChanged.emit(f)
        try: self.director.set_intensity(f)
        except Exception: pass
    def _on_blend_mode(self, idx: int):
        self.blendModeChanged.emit(idx)
        try: self.director.set_blend_mode(idx)
        except Exception: pass
    def _pick_color(self, arm: bool):
        from PyQt6.QtWidgets import QColorDialog
        col = QColorDialog.getColor(QColor("white" if arm else "black"), self)
        if not col.isValid(): return
        self._apply_color(arm, col)
    def _apply_color(self, arm: bool, col: QColor):
        rgba = (col.redF(), col.greenF(), col.blueF(), col.alphaF())
        if arm:
            self._arm_rgba = rgba; self.armColorChanged.emit(rgba)
            try: self.director.set_arm_color(col.redF(), col.greenF(), col.blueF())
            except Exception: pass
        else:
            self._gap_rgba = rgba; self.gapColorChanged.emit(rgba)
            try: self.director.set_gap_color(col.redF(), col.greenF(), col.blueF())
            except Exception: pass
    
    def _on_spiral_type(self, idx: int):
        """Handle spiral type selection (1-7)."""
        spiral_type = idx + 1  # ComboBox index 0-6 maps to spiral types 1-7
        try:
            self.director.set_spiral_type(spiral_type)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to set spiral type: {e}")
    
    def _on_spiral_width(self, idx: int):
        """Handle spiral width selection."""
        # Map index to spiral width in degrees
        widths = [60, 72, 90, 120, 180, 360]
        spiral_width = widths[idx] if idx < len(widths) else 60
        try:
            self.director.set_spiral_width(spiral_width)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to set spiral width: {e}")
    
    def _on_rotation_speed(self, value: int):
        """Handle rotation speed slider (400-4000 -> 4.0-40.0x)."""
        speed = value / 100.0  # Convert to 4.0-40.0 range
        self.rotationSpeedChanged.emit(speed)
        try:
            self.director.set_rotation_speed(speed)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to set rotation speed: {e}")
    
    def _on_max_zoom(self, value: int):
        """Handle max zoom slider (100-300 -> 1.0x-3.0x zoom)."""
        zoom = value / 100.0  # Convert to 1.0-3.0 range
        self.zoomSpeedChanged.emit(zoom)  # Reuse signal name for compatibility
        try:
            if self.compositor and hasattr(self.compositor, 'set_zoom_target'):
                self.compositor.set_zoom_target(zoom)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to set max zoom: {e}")

    def _on_media_mode(self, index: int):
        """Handle media mode selection (0=images&videos, 1=images only, 2=video focus)."""
        self.mediaModeChanged.emit(index)
        # This will be connected to visual director or loader to filter media
        import logging
        mode_names = ["Images & Videos", "Images Only", "Video Focus (Not Ready)"]
        logging.getLogger(__name__).info(f"Media mode changed to: {mode_names[index]}")

    def _on_image_duration(self, value: int):
        """Handle image duration change (1-60 seconds)."""
        self.imageDurationChanged.emit(value)
        import logging
        logging.getLogger(__name__).info(f"Image duration changed to: {value} seconds")

    def _on_video_duration(self, value: int):
        """Handle video duration change (5-300 seconds)."""
        self.videoDurationChanged.emit(value)
        import logging
        logging.getLogger(__name__).info(f"Video duration changed to: {value} seconds")
    
    # ===== Custom Mode Control Locking =====
    
    def lock_controls(self):
        """Disable controls that custom modes manage.
        
        When a custom mode is active, it owns these settings:
        - Spiral type, width, rotation speed, opacity
        - Media mode, image/video duration
        - Max zoom
        
        Colors (arm/gap) remain unlocked as they're global settings.
        """
        import logging
        logging.getLogger(__name__).info("[MesmerLoom] Locking controls for custom mode")
        
        # Disable spiral controls (custom mode owns spiral settings)
        self.cmb_spiral_type.setEnabled(False)
        self.cmb_spiral_width.setEnabled(False)
        self.sld_rotation_speed.setEnabled(False)
        self.sld_intensity.setEnabled(False)  # Spiral opacity
        
        # Disable media controls (custom mode owns media cycling)
        self.cmb_media_mode.setEnabled(False)
        self.spin_image_duration.setEnabled(False)
        self.spin_video_duration.setEnabled(False)
        
        # Disable zoom control (custom mode owns zoom settings)
        self.sld_max_zoom.setEnabled(False)
        
        # Blend mode stays enabled (can be adjusted globally)
        # Colors stay enabled (global settings)
    
    def unlock_controls(self):
        """Re-enable all controls when switching to built-in visual programs.
        
        Built-in visuals don't define their own settings, so user can
        adjust them via UI controls.
        """
        import logging
        logging.getLogger(__name__).info("[MesmerLoom] Unlocking controls for built-in visual")
        
        # Re-enable spiral controls
        self.cmb_spiral_type.setEnabled(True)
        self.cmb_spiral_width.setEnabled(True)
        self.sld_rotation_speed.setEnabled(True)
        self.sld_intensity.setEnabled(True)
        
        # Re-enable media controls
        self.cmb_media_mode.setEnabled(True)
        self.spin_image_duration.setEnabled(True)
        self.spin_video_duration.setEnabled(True)
        
        # Re-enable zoom control
        self.sld_max_zoom.setEnabled(True)

__all__ = ["PanelMesmerLoom"]
