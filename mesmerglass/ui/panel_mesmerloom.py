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
    spiralEnabledChanged = pyqtSignal(bool)
    intensityChanged = pyqtSignal(float)
    blendModeChanged = pyqtSignal(int)
    opacityChanged = pyqtSignal(float)
    armColorChanged = pyqtSignal(tuple)
    gapColorChanged = pyqtSignal(tuple)
    renderScaleChanged = pyqtSignal(float)

    def __init__(self, director, compositor, parent=None):
        super().__init__(parent)
        self.director = director; self.compositor = compositor
        self._arm_rgba = (1.0,1.0,1.0,1.0); self._gap_rgba = (0.0,0.0,0.0,1.0)
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(6,6,6,6); root.setSpacing(10)
        box_gen = QGroupBox("General"); lg = QVBoxLayout(box_gen); lg.setContentsMargins(8,8,8,8); lg.setSpacing(4)
        self.chk_enable = QCheckBox("Enable Spiral"); self.chk_enable.stateChanged.connect(lambda s: self._on_enable(bool(s)))
        lg.addWidget(self.chk_enable)
        self.sld_intensity = QSlider(Qt.Orientation.Horizontal); self.sld_intensity.setRange(0,100); lg.addWidget(_row("Intensity", self.sld_intensity))
        self.sld_intensity.valueChanged.connect(self._on_intensity)
        self.cmb_blend = QComboBox(); self.cmb_blend.addItems(["Multiply","Screen","SoftLight"]); self.cmb_blend.currentIndexChanged.connect(self._on_blend_mode)
        lg.addWidget(_row("Blend Mode", self.cmb_blend))
        self.sld_opacity = QSlider(Qt.Orientation.Horizontal); self.sld_opacity.setRange(20,100); self.sld_opacity.setValue(85); self.sld_opacity.valueChanged.connect(self._on_opacity)
        lg.addWidget(_row("Spiral Opacity", self.sld_opacity))
        self.spin_arms = QSpinBox(); self.spin_arms.setRange(2,8); self.spin_arms.setValue(4); self.spin_arms.valueChanged.connect(self._on_arm_count)
        lg.addWidget(_row("Arm Count", self.spin_arms))
        root.addWidget(box_gen)
        box_col = QGroupBox("Colors"); lc = QVBoxLayout(box_col); lc.setContentsMargins(8,8,8,8); lc.setSpacing(4)
        self.btn_arm_col = QPushButton("Arm Color"); self.btn_gap_col = QPushButton("Gap Color")
        self.btn_arm_col.clicked.connect(lambda: self._pick_color(True)); self.btn_gap_col.clicked.connect(lambda: self._pick_color(False))
        lc.addWidget(self.btn_arm_col); lc.addWidget(self.btn_gap_col)
        self.cmb_color_mode = QComboBox(); self.cmb_color_mode.addItems(["Flat","Radial","Drift"]); self.cmb_color_mode.currentIndexChanged.connect(self._on_color_mode)
        lc.addWidget(_row("Color Mode", self.cmb_color_mode))
        self.sld_mode_amount = QSlider(Qt.Orientation.Horizontal); self.sld_mode_amount.setRange(0,100); self.sld_mode_amount.valueChanged.connect(self._on_mode_amount)
        lc.addWidget(_row("Mode Amount", self.sld_mode_amount))
        root.addWidget(box_col)
        box_adv = QGroupBox("Advanced"); la = QVBoxLayout(box_adv); la.setContentsMargins(8,8,8,8); la.setSpacing(4)
        self.dsb_bw_base = QDoubleSpinBox(); self.dsb_bw_base.setRange(0.1,1.0); self.dsb_bw_base.setValue(0.5)
        self.dsb_bw_rng = QDoubleSpinBox(); self.dsb_bw_rng.setRange(0.0,0.5); self.dsb_bw_rng.setValue(0.1)
        self.dsb_bw_cyc = QDoubleSpinBox(); self.dsb_bw_cyc.setRange(1.0,600.0); self.dsb_bw_cyc.setValue(120.0)
        for w in (self.dsb_bw_base,self.dsb_bw_rng,self.dsb_bw_cyc): w.valueChanged.connect(self._on_bar_width_params)
        la.addWidget(_row("Bar Width (base)", self.dsb_bw_base)); la.addWidget(_row("Bar Width (range)", self.dsb_bw_rng)); la.addWidget(_row("Bar Width (cycle s)", self.dsb_bw_cyc))
        self.dsb_tw_base = QDoubleSpinBox(); self.dsb_tw_base.setRange(0.0,1.0); self.dsb_tw_base.setValue(0.06)
        self.dsb_tw_rng = QDoubleSpinBox(); self.dsb_tw_rng.setRange(0.0,0.5); self.dsb_tw_rng.setValue(0.05)
        self.dsb_tw_cyc = QDoubleSpinBox(); self.dsb_tw_cyc.setRange(1.0,600.0); self.dsb_tw_cyc.setValue(180.0)
        for w in (self.dsb_tw_base,self.dsb_tw_rng,self.dsb_tw_cyc): w.valueChanged.connect(self._on_twist_params)
        la.addWidget(_row("Twist (base)", self.dsb_tw_base)); la.addWidget(_row("Twist (range)", self.dsb_tw_rng)); la.addWidget(_row("Twist (cycle s)", self.dsb_tw_cyc))
        self.dsb_wob_amp = QDoubleSpinBox(); self.dsb_wob_amp.setRange(0.0,0.2); self.dsb_wob_amp.setValue(0.02)
        self.dsb_wob_cyc = QDoubleSpinBox(); self.dsb_wob_cyc.setRange(0.5,600.0); self.dsb_wob_cyc.setValue(2.0)
        for w in (self.dsb_wob_amp,self.dsb_wob_cyc): w.valueChanged.connect(self._on_wobble_params)
        la.addWidget(_row("Wobble amp", self.dsb_wob_amp)); la.addWidget(_row("Wobble cycle s", self.dsb_wob_cyc))
        self.dsb_flip_cad = QDoubleSpinBox(); self.dsb_flip_cad.setRange(5.0,3600.0); self.dsb_flip_cad.setValue(180.0)
        self.dsb_flip_wave = QDoubleSpinBox(); self.dsb_flip_wave.setRange(5.0,180.0); self.dsb_flip_wave.setValue(30.0)
        for w in (self.dsb_flip_cad,self.dsb_flip_wave): w.valueChanged.connect(self._on_flip_params)
        la.addWidget(_row("Flip cadence s", self.dsb_flip_cad)); la.addWidget(_row("Flip wave s", self.dsb_flip_wave))
        self.dsb_vignette = QDoubleSpinBox(); self.dsb_vignette.setRange(0.0,1.0); self.dsb_vignette.setValue(0.25); self.dsb_vignette.valueChanged.connect(self._on_vignette)
        la.addWidget(_row("Vignette", self.dsb_vignette))
        self.cmb_render_scale = QComboBox(); self.cmb_render_scale.addItems(["1.0","0.85","0.75"]); self.cmb_render_scale.currentTextChanged.connect(self._on_render_scale)
        la.addWidget(_row("Render Scale", self.cmb_render_scale))
        root.addWidget(box_adv)
        root.addStretch(1)

    # Helpers
    @staticmethod
    def _slider01(v: int) -> float: return max(0.0, min(1.0, v/100.0))
    @staticmethod
    def _opacity(v: int) -> float: return max(0.2, min(1.0, v/100.0))

    # Slots
    def _on_enable(self, en: bool):
        self.spiralEnabledChanged.emit(en)
        try: self.parent()._on_spiral_toggled(en)
        except Exception: pass
    def _on_intensity(self, v: int):
        f = self._slider01(v); self.intensityChanged.emit(f)
        try: self.director.set_intensity(f)
        except Exception: pass
    def _on_blend_mode(self, idx: int):
        self.blendModeChanged.emit(idx)
        try: self.director.set_blend_mode(idx)
        except Exception: pass
    def _on_opacity(self, v: int):
        f = self._opacity(v); self.opacityChanged.emit(f)
        try: self.director.set_opacity(f)
        except Exception: pass
    def _on_arm_count(self, v: int):
        try: self.director.set_arm_count(v)
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
        # Keep compositor call for any additional color processing
        try: self.compositor.set_color_params(self._arm_rgba, self._gap_rgba, self.cmb_color_mode.currentIndex(), {"amount": self._slider01(self.sld_mode_amount.value())})
        except Exception: pass
    def _on_color_mode(self, *_):
        try: self.compositor.set_color_params(self._arm_rgba, self._gap_rgba, self.cmb_color_mode.currentIndex(), {"amount": self._slider01(self.sld_mode_amount.value())})
        except Exception: pass
    def _on_mode_amount(self, v: int):
        try: self.compositor.set_color_params(self._arm_rgba, self._gap_rgba, self.cmb_color_mode.currentIndex(), {"amount": self._slider01(v)})
        except Exception: pass
    def _on_bar_width_params(self, *_):
        try: self.director.set_bar_width(self.dsb_bw_base.value(), self.dsb_bw_rng.value(), self.dsb_bw_cyc.value())
        except Exception: pass
    def _on_twist_params(self, *_):
        try: self.director.set_twist(self.dsb_tw_base.value(), self.dsb_tw_rng.value(), self.dsb_tw_cyc.value())
        except Exception: pass
    def _on_wobble_params(self, *_):
        try: self.director.set_wobble(self.dsb_wob_amp.value(), self.dsb_wob_cyc.value())
        except Exception: pass
    def _on_flip_params(self, *_):
        try: self.director.set_flip_cadence(self.dsb_flip_cad.value(), self.dsb_flip_wave.value())
        except Exception: pass
    def _on_vignette(self, v: float):
        try: self.director.set_vignette(v)
        except Exception: pass
    def _on_render_scale(self, txt: str):
        try: val = float(txt)
        except Exception: return
        self.renderScaleChanged.emit(val)
        try: self.compositor.set_render_scale(val)
        except Exception: pass

__all__ = ["PanelMesmerLoom"]
