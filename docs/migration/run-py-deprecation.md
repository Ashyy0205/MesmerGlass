# `run.py` Status (Updated November 2025)

We originally planned to remove `run.py` after finishing the argparse CLI. That plan changed once the Phase 7 MainApplication replaced the legacy launcher: the simplest way to launch the new UI is again `python run.py`.

## Current Behavior

- `python run.py` imports `mesmerglass.app.run()` and launches the MainApplication window.
- `python -m mesmerglass run` uses the same code path but keeps the CLI parser available for additional flags.
- Both entry points share logging, diagnostics, and environment flags (e.g., `MESMERGLASS_VR`).

## When to Use Which

| Scenario | Recommended command |
|----------|---------------------|
| End-user shortcut / double-click | `python run.py` |
| Need CLI flags (`--vr`, logging) | `python -m mesmerglass run --vr --log-level DEBUG` |
| Automation / CI tasks | `python -m mesmerglass <subcommand>` |

## Relationship to Other Subcommands

The argparse CLI remains the home for automation-friendly tasks (`selftest`, `pulse`, `server`, `test-run`, `state`, `spiral-measure`, etc.). `run.py` is deliberately tiny so packaged builds and Windows shortcuts can launch MesmerGlass without remembering CLI syntax.

## Migration Guidance

- Scripts that already use `python -m mesmerglass run` can stay that way—no change needed.
- Shell shortcuts or `.lnk` files that pointed to `python run.py` can keep doing so; there is no longer a deprecation warning.
- If you previously removed `run.py` from documentation, reintroduce it as “GUI shortcut” while keeping the CLI reference for advanced scenarios.

## Testing

To verify the shim:

```
python run.py            # Opens the GUI
python -m mesmerglass run
python -m mesmerglass selftest
```

All three should share the same version banner and logging format. If something diverges, capture the command, platform, and logs (use `--log-level DEBUG`) and open an issue.
