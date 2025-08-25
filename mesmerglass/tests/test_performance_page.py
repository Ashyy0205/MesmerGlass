import time, tempfile, os
import pytest
from mesmerglass.engine.perf import perf_metrics
from mesmerglass.ui.pages.performance import PerformancePage
from mesmerglass.engine.audio import Audio2
from PyQt6.QtWidgets import QApplication

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_metrics_basic():
    perf_metrics._frame_times.clear()  # type: ignore
    # Simulate 60 frames at 30 FPS -> dt=1/30
    for _ in range(60):
        perf_metrics.record_frame(1/30.0)
    snap = perf_metrics.snapshot()
    assert 29.5 < snap.fps < 30.5
    assert snap.avg_frame_ms and 32 < snap.avg_frame_ms < 35


def test_metrics_warnings():
    perf_metrics._frame_times.clear()  # type: ignore
    perf_metrics.target_fps = 60
    perf_metrics.warn_frame_ms = 10
    perf_metrics.warn_stall_ms = 5
    # Slow frames: 30 fps
    for _ in range(30):
        perf_metrics.record_frame(1/30.0)
    perf_metrics.record_io_stall(20)
    snap = perf_metrics.snapshot()
    assert any('Low FPS' in w for w in snap.warnings)
    assert any('I/O stall' in w for w in snap.warnings)


def test_performance_page_audio_memory(qapp):
    audio = Audio2()
    # Create temp files to simulate loaded sounds
    with tempfile.NamedTemporaryFile(delete=False) as f1, tempfile.NamedTemporaryFile(delete=False) as f2:
        f1.write(b'x'*2048); f1.flush()
        f2.write(b'y'*4096); f2.flush()
        audio.snd1_path = f1.name
        audio.snd2_path = f2.name
        page = PerformancePage(audio)
        # Process events to trigger refresh
        t0 = time.time()
        while time.time() - t0 < 0.3:
            qapp.processEvents()
            time.sleep(0.01)
        assert 'KB' in page.lab_a1.text() or 'MB' in page.lab_a1.text()
        assert 'KB' in page.lab_a2.text() or 'MB' in page.lab_a2.text()
    os.unlink(f1.name); os.unlink(f2.name)
