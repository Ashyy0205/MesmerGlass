# Deprecation: `run.py`

`run.py` has been replaced by the unified argparse CLI exposed via:

```
python -m mesmerglass <subcommand>
```

## Timeline
- Current release: `python run.py` still works but emits a `DeprecationWarning`.
- Future minor release: the shim will be removed.

## Mapping
| Old Command                       | New Command                                      |
|----------------------------------|--------------------------------------------------|
| `python run.py`                  | `python -m mesmerglass run`                      |
| `python run.py gui`              | `python -m mesmerglass run`                      |
| `python run.py server -p 12345`  | `python -m mesmerglass server --port 12345`      |
| `python run.py test -i .5 -d 500`| `python -m mesmerglass pulse --level .5 --duration 500` |
| *(tests)* `python run_tests.py`  | `python -m mesmerglass test-run`                 |

## Rationale
Maintaining two parallel CLIs (`run.py` and the package CLI) led to duplicated code and documentation drift. Consolidating on a single entry point:
- Removes redundant argument parsing & logging init
- Simplifies docs and onboarding
- Enables new subcommands (`test-run`) without legacy coupling

## What to Change
- Update scripts / shortcuts to call `python -m mesmerglass run`.
- Replace any CI references to `run_tests.py` with `python -m mesmerglass test-run`.

## Testing the Shim
Running `python run.py` now logs a deprecation warning and delegates to the new CLI. Behavior should remain identical aside from the warning.

If you experience issues with the CLI transition, open an issue with:
- Exact command used
- Python version / OS
- Log output (with `--log-level DEBUG` if possible)

---
Thanks for migrating! This cleanup keeps the project lean and easier to maintain.
