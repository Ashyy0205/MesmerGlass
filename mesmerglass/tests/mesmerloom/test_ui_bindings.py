import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor  # added for color construction

try:
    from mesmerglass.ui.panel_mesmerloom import PanelMesmerLoom
    from mesmerglass.mesmerloom.spiral import SpiralDirector
except Exception:  # pragma: no cover
    PanelMesmerLoom = None  # type: ignore
    SpiralDirector = None  # type: ignore

class DummyCompositor:
    def __init__(self):
        self.calls = []
        self._blend_mode = 0
        self._opacity = 0.0
        self._render_scale = 1.0
        self._arm_count = 4
        self._arm_rgba = None
    def set_blend_mode(self, m:int): self._blend_mode = m; self.calls.append(("blend", m))
    def set_opacity(self, f:float): self._opacity = f; self.calls.append(("opacity", f))
    def set_render_scale(self, f:float): self._render_scale = f; self.calls.append(("scale", f))
    def set_color_params(self, arm, gap, mode, grad): self._arm_rgba = arm; self.calls.append(("color", arm))
    def set_arm_count(self, n:int): self._arm_count = n; self.calls.append(("arms", n))

@pytest.mark.skipif(PanelMesmerLoom is None, reason="PanelMesmerLoom unavailable")
def test_panel_live_updates(qtbot):
    app = QApplication.instance() or QApplication([])
    director = SpiralDirector(seed=1)
    comp = DummyCompositor()
    panel = PanelMesmerLoom(director, comp)
    qtbot.addWidget(panel)
    # a) Enable
    panel.chk_enable.setChecked(True)
    assert panel.chk_enable.isChecked()
    # b) Intensity -> 100
    panel.sld_intensity.setValue(100)
    assert abs(director._pending_intensity - 1.0) < 1e-6
    # c) Blend mode Screen -> index 1
    panel.cmb_blend.setCurrentIndex(1)
    assert comp._blend_mode == 1
    # d) Arm color change via helper
    panel.test_set_arm_color(0.25,0.5,0.75,1.0) if hasattr(panel,'test_set_arm_color') else panel._apply_color(True, QColor.fromRgbF(0.25,0.5,0.75,1.0))
    assert comp._arm_rgba is not None and abs(comp._arm_rgba[0]-0.25)<1e-3
    # e) Render scale
    panel.cmb_render_scale.setCurrentText("0.85")
    assert abs(comp._render_scale - 0.85) < 1e-6
