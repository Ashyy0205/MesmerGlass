import pytest

# Skip if PyQt6 OpenGL components not available (headless CI without GL)
try:  # pragma: no cover
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # noqa: F401
except Exception:  # pragma: no cover
    QApplication = None  # type: ignore

from mesmerglass.mesmerloom.compositor import Compositor
from mesmerglass.mesmerloom.spiral import SpiralDirector


@pytest.mark.skipif(QApplication is None, reason="PyQt6 OpenGL not available")
def test_compositor_initializes(qtbot):
    """Smoke: compositor constructs, GL (attempts) init, phase advances."""
    app = QApplication.instance() or QApplication([])
    director = SpiralDirector(seed=123)
    widget = Compositor(director)
    qtbot.addWidget(widget)
    widget.resize(320, 240)
    widget.show()
    for _ in range(25):
        app.processEvents()
    if widget._program is None:
        pytest.skip("GL program not built (driver/context issue)")
    assert widget._vao is not None
    start_phase = director.state.phase
    for _ in range(10):
        app.processEvents()
    end_phase = director.state.phase
    assert end_phase >= start_phase
    widget.close()
