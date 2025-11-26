import os
from PyQt6.QtWidgets import QProgressBar, QLabel
from mesmerglass.ui.dialogs.cuelist_loading_dialog import CuelistLoadingDialog


def test_loading_dialog_updates_progress(qtbot):
    dialog = CuelistLoadingDialog(total_files=3)
    qtbot.addWidget(dialog)
    dialog.show()

    progress_bar: QProgressBar = dialog.findChild(QProgressBar, "cuelistAudioProgressBar")
    status_label: QLabel = dialog.findChild(QLabel, "cuelistAudioStatusLabel")

    dialog.update_progress(1, 3, os.path.join("tmp", "a.mp3"), True)
    assert progress_bar.value() == 1
    assert "a.mp3" in status_label.text()

    dialog.update_progress(2, 3, os.path.join("tmp", "b.mp3"), False)
    assert progress_bar.value() == 2
    assert "Failed" in status_label.text()

    dialog.mark_complete(failures=1)
    assert "warning" in status_label.text().lower()