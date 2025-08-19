# MesmerGlass Roadmap (Prioritized Milestones)

Focused, incremental milestones in the exact order we’ll implement them. Each milestone lists scope, impacted components, tests/docs, and success criteria.

— Last Updated: August 19, 2025 —

## 1) Device Sync improvements (no auto-select, multi-select, show connected) [DONE]

- Scope
  - Remove auto-selection/auto-connect side effects when scanning.
  - Allow selecting multiple devices; clearly visualize connected vs available.
  - Persist last selections across sessions (opt-in) without auto-connecting.
- Impacted
  - UI: `mesmerglass/ui/pages/device_sync.py` (selection widgets, state), `mesmerglass/ui/launcher.py` (init flags), overlays as-needed.
  - Engine: `mesmerglass/engine/device_manager.py` (selection model, connection orchestration).
  - CLI: `mesmerglass/cli.py` optional verbs (e.g., `device --list / --select IDs --status`).
- Tests
  - Add unit tests for selection model and connection orchestration.
  - CLI smoke: list/select/status in headless mode.
- Success
  - No device connects without explicit action.
  - Multi-select works; connected state visible and accurate.
  - Zero regressions in Bluetooth tests.

## 2) Virtual Toy devtool (for development and CI)

- Scope
  - Provide a lightweight simulator for 1–2 device types with latency and intensity mapping.
  - Expose via CLI (dev-only) and integrate into tests.
- Impacted
  - Tests/util: `mesmerglass/tests/virtual_toy.py` (enhanced); new `mesmerglass/ui/devtools.py` (if kept minimal) or CLI-only entry.
  - Docs: clear dev/CI usage notes.
- Tests
  - Deterministic behaviors exercised in pytest; no flakiness on Windows.
- Success
  - End-to-end CLI/UI flows can run without real hardware.

## 3) Sessions & “Message Packs” (JSON content bundles)

- Scope
  - Define minimal JSON format for session state: text sequences, pulsing stages, fallback behaviors.
  - Load/apply packs from disk; no complex editor yet.
- Minimal schema
  ```json
  {
    "version": 1,
    "name": "Sample",
    "text": { "items": [ { "msg": "Relax", "secs": 10 } ] },
    "pulse": { "stages": [ { "mode": "wave", "intensity": 0.4, "secs": 20 } ], "fallback": "idle" }
  }
  ```
- Impacted
  - New: `mesmerglass/content/loader.py` and `mesmerglass/content/models.py`.
  - UI glue in `launcher.py` to apply a pack quickly.
- Tests
  - Round-trip load/apply; validation errors; CLI to apply a pack and print status.
- Success
  - Pack loads in < 200 ms and maps to current UI/engine state.

## 4) Text editing, fonts, and simple layouts

- Scope
  - Text page gains an editor feel: multiple sentences/entries; basic ordering.
  - Font import (local TTF/OTF) and per-entry scale.
- Impacted
  - UI pages under `mesmerglass/ui/pages/` (Text & FX); resource handling.
- Tests
  - Non-interactive: ensure font load succeeds; basic render path smoke.
- Success
  - Users can add/edit multiple text entries and choose fonts without crash.

## 5) Performance page and warnings

- Scope
  - New page/panel that surfaces FPS, frame timing, and I/O stalls; simple warnings when thresholds exceeded.
- Impacted
  - UI: `mesmerglass/ui/pages/` new `performance.py`; minor taps in audio/video engines for metrics.
- Tests
  - Headless smoke ensuring metrics report structure; thresholds configurable.
- Success
  - Clear, actionable warnings appear during stress; no UI freezes.

## 6) Audio memory improvements

- Scope
  - Stream audio (chunked) instead of loading entire files; configurable buffers.
- Impacted
  - `mesmerglass/engine/audio.py` and related playback loop.
- Tests
  - Memory footprint comparison mocks; long-file playback smoke.
- Success
  - ≥70% reduction vs baseline on large files without stutter under default settings.

## 7) Hotkeys (safety and control)

- Scope
  - Global hotkeys: Emergency Stop, Pause/Resume, Intensity up/down.
- Impacted
  - `mesmerglass/ui/hotkeys.py`; integration hooks in `launcher.py`.
- Notes
  - Prefer OS-friendly, optional enablement; avoid heavy deps unless necessary.
- Success
  - Works on Windows reliably; can be disabled in CI.

## 8) Log panel (overlay and engine logs)

- Scope
  - In-app log viewer with filters (audio/video/device/BLE); quick export.
- Impacted
  - `mesmerglass/ui/log_panel.py` (new) and wiring in `launcher.py`.
- Success
  - Realtime logs visible; zero “I/O on closed file” regressions.

## 9) Heart-rate integration (Galaxy Watch as test device)

- Scope
  - BLE Heart Rate Service (0x180D) reader; expose BPM and RR intervals.
- Impacted
  - New: `mesmerglass/biometric/heart_rate.py`; basic UI panel for display.
- Tests
  - Parser/unit tests; optional simulator feed in CI.
- Success
  - Stable readings; UI shows live BPM; safe teardown.

## 10) HR-based edging algorithm (adaptive control)

- Scope
  - Simple adaptive engine that maps BPM to staged intensity with safety caps.
- Impacted
  - New: `mesmerglass/biometric/adaptive_engine.py`; glue into device manager.
- Tests
  - Unit tests for mapping curves and saturation; integration with virtual toy.
- Success
  - Smooth, bounded adjustments; manual override remains available.

---

### Deliverables and cross-cutting requirements

- CLI
  - Keep `argparse`; add verbs only when they unlock testing/CI or real UX.
  - Always provide `--help` and non-zero exit codes on errors.
- Tests
  - Add PyTest coverage for each milestone, including CLI tests where applicable.
- Docs
  - Update `docs/` and this roadmap as features land; add `docs/cli.md` examples when verbs change.
- Safety and performance
  - Maintain clean shutdown; prefer ephemeral ports on Windows; keep UI hidden in CI by default.

---

### Timeline (high-level; adjust as needed)

- Aug–Sep 2025: 1–3 (Device sync, Virtual toy, Message packs)
- Oct 2025: 4–5 (Text/fonts, Performance page)
- Nov 2025: 6–7 (Audio memory, Hotkeys)
- Dec 2025–Jan 2026: 8–10 (Logs, HR integration, Adaptive)
