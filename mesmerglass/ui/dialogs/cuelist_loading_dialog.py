"""Modal progress dialog displayed while cuelist audio is prepared."""

from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar


class CuelistLoadingDialog(QDialog):
    """Shows a simple progress bar while audio assets are preloaded."""

    def __init__(self, *, total_files: int, parent=None) -> None:
        super().__init__(parent)
        self._total_files = max(0, total_files)
        self.setWindowTitle("Preparing Audio Tracks")
        self.setModal(True)
        # Prevent users from dismissing the dialog mid-load to avoid odd states.
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self._status_label = QLabel("Scanning cuelist audio…")
        self._status_label.setObjectName("cuelistAudioStatusLabel")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("cuelistAudioProgressBar")
        self._progress_bar.setRange(0, self._total_files or 1)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

    def update_progress(self, completed: int, total: int, file_path: str, success: bool) -> None:
        """Update the label and bar as each audio file finishes preloading."""
        max_value = max(1, total)
        if self._progress_bar.maximum() != max_value:
            self._progress_bar.setMaximum(max_value)
        self._progress_bar.setValue(min(completed, max_value))

        status = "Prefetched" if success else "Failed"
        filename = Path(file_path).name
        self._status_label.setText(f"{status} {completed}/{total}: {filename}")

    def mark_complete(self, failures: int) -> None:
        """Provide a final summary before the dialog closes."""
        if failures:
            self._status_label.setText(
                f"Completed with {failures} warning{'s' if failures != 1 else ''}."
            )
        else:
            self._status_label.setText("All audio tracks are ready.")

        self._progress_bar.setValue(self._progress_bar.maximum())