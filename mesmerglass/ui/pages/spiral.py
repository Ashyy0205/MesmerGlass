"""Spiral overlay settings page (minimal stub).

This lightweight page exposes a few primary controls; deeper tuning hidden for now.
"""
from __future__ import annotations
from PyQt6 import QtWidgets, QtCore
from .. import widgets as mw

class SpiralPage(QtWidgets.QWidget):
    spiralToggled = QtCore.pyqtSignal(bool)
    intensityChanged = QtCore.pyqtSignal(float)
    opacityChanged = QtCore.pyqtSignal(float)
    armsChanged = QtCore.pyqtSignal(int)

    def __init__(self, app_ctx, spiral_director, parent=None):
        super().__init__(parent)
        self.app_ctx = app_ctx
        self.director = spiral_director
        lay = QtWidgets.QVBoxLayout(self)
        # Enable toggle
        self.chk_enable = QtWidgets.QCheckBox("Enable Spiral Overlay")
        self.chk_enable.setChecked(False)
        lay.addWidget(self.chk_enable)
        # Intensity slider 0..100 mapped to 0..1
        self.sld_intensity = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.sld_intensity.setRange(0,100)
        self.sld_intensity.setValue(int(self.director.cfg.intensity*100))
        lay.addWidget(QtWidgets.QLabel("Intensity"))
        lay.addWidget(self.sld_intensity)
        # Opacity slider
        self.sld_opacity = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.sld_opacity.setRange(30,100)
        self.sld_opacity.setValue(int(self.director.cfg.opacity*100))
        lay.addWidget(QtWidgets.QLabel("Opacity"))
        lay.addWidget(self.sld_opacity)
        # Arms spinner using existing UnitSpin control
        self.spin_arms = mw.UnitSpin(minimum=2, maximum=8, value=self.director.cfg.arms, unit=" arms")
        lay.addWidget(self.spin_arms)
        lay.addStretch(1)
        self.chk_enable.toggled.connect(self.spiralToggled.emit)
        self.sld_intensity.valueChanged.connect(self._on_intensity)
        self.sld_opacity.valueChanged.connect(self._on_opacity)
        self.spin_arms.valueChanged.connect(self._on_arms)

    def _on_intensity(self, v: int):
        f = v/100.0
        self.director.set_intensity(f, abrupt=True)
        self.intensityChanged.emit(f)

    def _on_opacity(self, v: int):
        op = v/100.0
        self.director.set_opacity(op)
        self.opacityChanged.emit(op)

    def _on_arms(self, v: int):
        self.director.set_arm_count(int(v))
        self.armsChanged.emit(int(v))

__all__ = ["SpiralPage"]
