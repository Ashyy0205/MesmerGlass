# Developer Tools and Dev-only Scripts

This page catalogs helper scripts and diagnostics intended for development and manual QA. These are not part of the end-user flow.

## Dev-only scripts (archived)

Moved to `scripts/dev-archive/` to keep the repo root clean:

- `test_mode_workflow.py` — programmatically creates a sample mode JSON and outlines manual validation steps.
- `test_subtext_spacing.py` — prints spacing metrics for SUBTEXT mode for various message lengths.
- `test_subtext_scaled.py` — similar to above but demonstrates scale-aware spacing.
- `visual_mode_Custom_Mode_*.txt` — sample mode summaries exported during development.

## Actively used tools

- `scripts/visual_mode_creator.py` — design and export custom visual modes (JSON).
- `scripts/quick_speed_test.py`, `scripts/multi_speed_test.py` — performance probes for benchmarking.
- `scripts/visual_programs_ui.py`, `scripts/visual_mode_creator.py` — UI harnesses for visuals.
- `python -m mesmerglass mode-verify` — headless verification for mode timing and RPM equivalence.

## Notes

- For timing checks and equivalence, prefer `mode-verify` and the unit tests in `mesmerglass/tests`.
- If you generate new ad-hoc helper scripts, place them in `scripts/dev-archive/` or extend this page.
