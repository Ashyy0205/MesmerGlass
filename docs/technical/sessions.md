## Session / Message Packs (v1)

Lightweight JSON bundles describing initial session intent. Versioned; v1 only
applies *initial* state (first text message + average intensity heuristic).

### Schema (v1)
```json
{
  "version": 1,
  "name": "Sample",
  "text": { "items": [ { "msg": "Relax", "secs": 10 } ] },
  "pulse": { "stages": [ { "mode": "wave", "intensity": 0.4, "secs": 20 } ], "fallback": "idle" }
}
```

### CLI
```
python -m mesmerglass session --load pack.json --summary
python -m mesmerglass session --load pack.json --print
python -m mesmerglass session --load pack.json --apply
```

### Modes
- `--summary` (default) => single line summary
- `--print` => canonical minimized JSON
- `--apply` => headless apply, prints `{pack, text, buzz_intensity}` JSON

### Validation
- version == 1
- positive ints for secs
- intensity in [0,1]
- non-empty strings
- size < 1MB

### Mapping (v1)
| Pack | Launcher | Notes |
|------|----------|-------|
| first text item.msg | text | Updates Text & FX page label |
| avg intensity | buzz_intensity | heuristic only |

### Performance
Target <200ms typical (test permits <500ms).

### Future
Timers, progression, patterns, editor UI, persistence.
