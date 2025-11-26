"""
Quick test of the Cue Editor Dialog
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from mesmerglass.session.cue import Cue, PlaybackEntry, PlaybackSelectionMode
from mesmerglass.ui.cue_editor_dialog import CueEditorDialog


def test_cue_editor():
    """Test the cue editor dialog."""
    app = QApplication(sys.argv)
    
    # Create a test cue
    cue = Cue(
        name="Test Cue",
        duration_seconds=30.0,
        selection_mode=PlaybackSelectionMode.ON_MEDIA_CYCLE,
        playback_pool=[
            PlaybackEntry(
                playback_path=Path("1"),
                weight=1.0,
                min_duration_s=5.0,
                max_duration_s=10.0,
                text_messages=["Focus", "Relax", "Drift"]
            ),
            PlaybackEntry(
                playback_path=Path("2"),
                weight=2.0,
                min_duration_s=7.0,
                max_duration_s=15.0,
                text_messages=None
            )
        ]
    )
    
    # Available playbacks
    available_playbacks = ["1", "2", "3"]
    
    # Open dialog
    dialog = CueEditorDialog(cue, available_playbacks)
    result = dialog.exec()
    
    if result:
        print("Dialog accepted! Cue data:")
        print(f"  Name: {cue.name}")
        print(f"  Duration: {cue.duration_seconds}s")
        print(f"  Selection Mode: {cue.selection_mode}")
        print(f"  Playback Pool ({len(cue.playback_pool)} entries):")
        for i, entry in enumerate(cue.playback_pool, 1):
            print(f"    {i}. {entry.playback_path}")
            print(f"       Weight: {entry.weight}")
            print(f"       Duration: {entry.min_duration_s}-{entry.max_duration_s}s")
            if entry.text_messages:
                print(f"       Text: {entry.text_messages}")
    else:
        print("Dialog cancelled")


if __name__ == "__main__":
    test_cue_editor()
