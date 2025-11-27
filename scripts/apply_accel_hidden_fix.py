"""Apply accelerate hidden-disable adjustments to playback_editor.py."""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "mesmerglass" / "ui" / "editors" / "playback_editor.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if old not in source:
        print(f"[apply_accel_hidden_fix] Failed to locate block: {label}", file=sys.stderr)
        sys.exit(1)
    return source.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    old_block = (
        "        self._accelerate_last_media_speed = None\n"
        "        self._accelerate_media_speed_target = None\n"
        "        self._accelerate_media_speed_smoothed = None\n"
        "        self._accelerate_auto_enable_pending = False\n"
    )
    new_block = (
        "        self._accelerate_last_media_speed = None\n"
        "        self._accelerate_media_speed_target = None\n"
        "        self._accelerate_media_speed_smoothed = None\n"
        "        self._accelerate_hidden_disabled = False\n"
        "        self._accelerate_auto_enable_pending = False\n"
    )
    text = replace_once(text, old_block, new_block, "accelerate attribute block")

    old_block = (
        "    def _is_accelerate_enabled(self) -> bool:\n"
        "        return hasattr(self, \"accelerate_enable_check\") and self.accelerate_enable_check.isChecked()\n"
        "\n"
    )
    new_block = old_block + (
        "    def _is_accelerate_active(self) -> bool:\n"
        "        return self._is_accelerate_enabled() and not self._accelerate_hidden_disabled\n\n"
        "    def _set_accelerate_hidden_disabled(self, hidden: bool) -> None:\n"
        "        if self._accelerate_hidden_disabled == hidden:\n"
        "            return\n"
        "        self._accelerate_hidden_disabled = hidden\n"
        "        if hidden:\n"
        "            if self._accelerate_overriding:\n"
        "                self._accelerate_overriding = False\n"
        "                self._restore_base_dynamic_controls()\n"
        "            self._update_accelerate_state_label()\n"
        "            return\n"
        "        if self._is_accelerate_enabled():\n"
        "            self._reset_accelerate_progress()\n"
        "        else:\n"
        "            self._update_accelerate_state_label()\n\n"
        "    def _update_accelerate_state_label(\n"
        "        self, *, progress: float | None = None, rotation: float | None = None,\n"
        "        media: float | None = None, zoom: float | None = None\n"
        "    ) -> None:\n"
        "        if not hasattr(self, \"accelerate_state_label\"):\n"
        "            return\n"
        "        if not self._is_accelerate_enabled():\n"
        "            self.accelerate_state_label.setText(\"Disabled\")\n"
        "            return\n"
        "        if self._accelerate_hidden_disabled:\n"
        "            self.accelerate_state_label.setText(\"Synchronizing presets...\")\n"
        "            return\n"
        "        if None not in (progress, rotation, media, zoom):\n"
        "            self.accelerate_state_label.setText(\n"
        "                f\"{progress * 100:5.1f}%  rot {rotation:.1f}x  media {media:.0f}  zoom {zoom:.2f}\"\n"
        "            )\n"
        "            return\n"
        "        self.accelerate_state_label.setText(\"Ready\")\n\n"
    )
    text = replace_once(text, old_block, new_block, "accelerate helpers block")

    old_block = (
        "    def _on_accelerate_enabled_changed(self, state):\n"
        "        \"\"\"Enable/disable accelerate ramp controls.\"\"\"\n"
        "        enabled = state == Qt.CheckState.Checked\n"
        "        self._accelerate_auto_enable_pending = False\n"
        "        self._accelerate_auto_enable_scheduled = False\n"
        "        self._cancel_accelerate_auto_enable_timer()\n"
        "        if not enabled and hasattr(self, \"accelerate_state_label\"):\n"
        "            self.accelerate_state_label.setText(\"Disabled\")\n\n"
        "        self._mark_modified()\n"
        "        self._reset_accelerate_progress()\n\n"
        "        if not enabled and self._accelerate_overriding:\n"
        "            self._accelerate_overriding = False\n"
        "            self._restore_base_dynamic_controls()\n\n\n"
    )
    new_block = (
        "    def _on_accelerate_enabled_changed(self, state):\n"
        "        \"\"\"Enable/disable accelerate ramp controls.\"\"\"\n"
        "        enabled = state == Qt.CheckState.Checked\n"
        "        self._accelerate_auto_enable_pending = False\n"
        "        self._accelerate_auto_enable_scheduled = False\n"
        "        self._cancel_accelerate_auto_enable_timer()\n"
        "        if self._accelerate_hidden_disabled:\n"
        "            self._set_accelerate_hidden_disabled(False)\n\n"
        "        self._mark_modified()\n"
        "        self._reset_accelerate_progress()\n\n"
        "        if not enabled and self._accelerate_overriding:\n"
        "            self._accelerate_overriding = False\n"
        "            self._restore_base_dynamic_controls()\n"
        "        self._update_accelerate_state_label()\n\n\n"
    )
    text = replace_once(text, old_block, new_block, "accelerate toggle handler")

    old_block = (
        "    def _reset_accelerate_progress(self):\n"
        "        \"\"\"Reset accelerate timing window.\"\"\"\n"
        "        if not hasattr(self, \"accelerate_enable_check\"):\n"
        "            return\n\n"
        "        if self._is_accelerate_enabled():\n"
        "            self._accelerate_start_time = time.time()\n"
        "            self._accelerate_progress = 0.0\n"
        "            # Clear ramp bookkeeping so freshly loaded playbacks restart timers immediately\n"
        "            self._accelerate_overriding = False\n"
        "            self._accelerate_last_media_speed = None\n"
        "            self._accelerate_media_speed_target = None\n"
        "            self._accelerate_media_speed_smoothed = None\n"
        "            self._accelerate_last_interval_update_ts = None\n"
        "        else:\n"
        "            self._accelerate_start_time = None\n"
        "            self._accelerate_progress = 0.0\n"
        "            self._accelerate_overriding = False\n"
        "            if hasattr(self, \"accelerate_state_label\"):\n"
        "                self.accelerate_state_label.setText(\"Disabled\")\n"
        "            self._accelerate_last_media_speed = None\n"
        "            self._accelerate_media_speed_target = None\n"
        "            self._accelerate_media_speed_smoothed = None\n"
        "            self._accelerate_last_interval_update_ts = None\n\n"
    )
    new_block = (
        "    def _reset_accelerate_progress(self):\n"
        "        \"\"\"Reset accelerate timing window.\"\"\"\n"
        "        if not hasattr(self, \"accelerate_enable_check\"):\n"
        "            return\n\n"
        "        if self._is_accelerate_active():\n"
        "            self._accelerate_start_time = time.time()\n"
        "            self._accelerate_progress = 0.0\n"
        "            # Clear ramp bookkeeping so freshly loaded playbacks restart timers immediately\n"
        "            self._accelerate_overriding = False\n"
        "            self._accelerate_last_media_speed = None\n"
        "            self._accelerate_media_speed_target = None\n"
        "            self._accelerate_media_speed_smoothed = None\n"
        "            self._accelerate_last_interval_update_ts = None\n"
        "        else:\n"
        "            self._accelerate_start_time = None\n"
        "            self._accelerate_progress = 0.0\n"
        "            self._accelerate_overriding = False\n"
        "            self._accelerate_last_media_speed = None\n"
        "            self._accelerate_media_speed_target = None\n"
        "            self._accelerate_media_speed_smoothed = None\n"
        "            self._accelerate_last_interval_update_ts = None\n"
        "        self._update_accelerate_state_label()\n\n"
    )
    text = replace_once(text, old_block, new_block, "accelerate reset")

    old_block = (
        "    def _auto_enable_accelerate_if_pending(self):\n"
        "        self._cancel_accelerate_auto_enable_timer()\n"
        "        if not self._accelerate_auto_enable_pending:\n"
        "            return\n"
        "        self._accelerate_auto_enable_pending = False\n"
        "        if not hasattr(self, \"accelerate_enable_check\"):\n"
        "            return\n"
        "        if self.accelerate_enable_check.isChecked():\n"
        "            return\n"
        "        logger.info(\"[PlaybackEditor] Auto-enabling accelerate preset after startup\")\n"
        "        self.accelerate_enable_check.setChecked(True)\n\n"
    )
    new_block = (
        "    def _auto_enable_accelerate_if_pending(self):\n"
        "        self._cancel_accelerate_auto_enable_timer()\n"
        "        if not self._accelerate_auto_enable_pending:\n"
        "            return\n"
        "        self._accelerate_auto_enable_pending = False\n"
        "        if not hasattr(self, \"accelerate_enable_check\"):\n"
        "            return\n"
        "        if not self._is_accelerate_enabled():\n"
        "            logger.info(\"[PlaybackEditor] Auto-enabling accelerate preset after startup\")\n"
        "            self.accelerate_enable_check.setChecked(True)\n"
        "            return\n"
        "        if self._accelerate_hidden_disabled:\n"
        "            logger.info(\"[PlaybackEditor] Releasing hidden accelerate disable after startup\")\n"
        "            self._set_accelerate_hidden_disabled(False)\n\n"
    )
    text = replace_once(text, old_block, new_block, "auto-enable block")

    old_block = (
        "    def _update_accelerate_effects(self):\n"
        "        \"\"\"Apply accelerate overrides each frame when enabled.\"\"\"\n"
        "        if not PREVIEW_AVAILABLE or not hasattr(self, \"accelerate_enable_check\"):\n"
        "            return\n\n"
        "        if not self._is_accelerate_enabled():\n"
        "            if self._accelerate_overriding:\n"
        "                self._accelerate_overriding = False\n"
        "                self._restore_base_dynamic_controls()\n"
        "            return\n\n"
    )
    new_block = (
        "    def _update_accelerate_effects(self):\n"
        "        \"\"\"Apply accelerate overrides each frame when enabled.\"\"\"\n"
        "        if not PREVIEW_AVAILABLE or not hasattr(self, \"accelerate_enable_check\"):\n"
        "            return\n\n"
        "        if not self._is_accelerate_active():\n"
        "            if self._accelerate_overriding:\n"
        "                self._accelerate_overriding = False\n"
        "                self._restore_base_dynamic_controls()\n"
        "            self._update_accelerate_state_label()\n"
        "            return\n\n"
    )
    text = replace_once(text, old_block, new_block, "accelerate update header")

    old_block = (
        "        if hasattr(self, \"accelerate_state_label\"):\n"
        "            self.accelerate_state_label.setText(\n"
        "                f\"{progress * 100:5.1f}%  rot {rotation_x:.1f}x  media {media_speed:.0f}  zoom {zoom_rate:.2f}\"\n"
        "            )\n\n"
    )
    new_block = (
        "        self._update_accelerate_state_label(\n"
        "            progress=progress,\n"
        "            rotation=rotation_x,\n"
        "            media=media_speed,\n"
        "            zoom=zoom_rate,\n"
        "        )\n\n"
    )
    text = replace_once(text, old_block, new_block, "accelerate label update")

    old_block = (
        "        if hasattr(self, \"accelerate_state_label\") and not self._is_accelerate_enabled():\n"
        "            self.accelerate_state_label.setText(\"Disabled\")\n\n"
    )
    new_block = "        self._update_accelerate_state_label()\n\n"
    text = replace_once(text, old_block, new_block, "restore base label")

    old_block = (
        "        self._cancel_accelerate_auto_enable_timer()\n"
        "        self._accelerate_auto_enable_pending = accel_enabled\n"
        "        self._accelerate_auto_enable_scheduled = False\n\n"
        "        self.accelerate_enable_check.blockSignals(True)\n"
        "        # Start with accelerate disabled; we'll auto-toggle it back on after timers stabilize.\n"
        "        self.accelerate_enable_check.setChecked(False)\n"
        "        self.accelerate_enable_check.blockSignals(False)\n\n"
        "        self.accelerate_duration_slider.blockSignals(True)\n"
        "        duration_clamped = max(self.accelerate_duration_slider.minimum(), min(self.accelerate_duration_slider.maximum(), int(accel_duration)))\n"
        "        self.accelerate_duration_slider.setValue(duration_clamped)\n"
        "        self.accelerate_duration_slider.blockSignals(False)\n\n"
        "        self._update_accelerate_duration_label(duration_clamped)\n"
        "        self.accelerate_state_label.setText(\"Disabled\")\n"
    )
    new_block = (
        "        self._cancel_accelerate_auto_enable_timer()\n"
        "        self._accelerate_auto_enable_pending = accel_enabled\n"
        "        self._accelerate_auto_enable_scheduled = False\n\n"
        "        self.accelerate_enable_check.blockSignals(True)\n"
        "        self.accelerate_enable_check.setChecked(accel_enabled)\n"
        "        self.accelerate_enable_check.blockSignals(False)\n\n"
        "        if accel_enabled:\n"
        "            self._accelerate_hidden_disabled = False\n"
        "            self._set_accelerate_hidden_disabled(True)\n"
        "        else:\n"
        "            self._accelerate_hidden_disabled = False\n"
        "            self._update_accelerate_state_label()\n\n"
        "        self.accelerate_duration_slider.blockSignals(True)\n"
        "        duration_clamped = max(self.accelerate_duration_slider.minimum(), min(self.accelerate_duration_slider.maximum(), int(accel_duration)))\n"
        "        self.accelerate_duration_slider.setValue(duration_clamped)\n"
        "        self.accelerate_duration_slider.blockSignals(False)\n\n"
        "        self._update_accelerate_duration_label(duration_clamped)\n"
    )
    text = replace_once(text, old_block, new_block, "load accelerate block")

    TARGET.write_text(text, encoding="utf-8")
    print("[apply_accel_hidden_fix] Accelerate hidden-disable fix applied.")


if __name__ == "__main__":
    main()
