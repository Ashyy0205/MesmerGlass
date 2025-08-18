# Mesmer Glass (Modular Dev Layout)

## Run (dev)
```powershell
python -m pip install -r requirements.txt
python run.py
```
Or as a module:
```powershell
python -m mesmerglass.app
```

## Structure
- `mesmerglass/engine/` — video, audio, buttplug pulse
- `mesmerglass/ui/` — overlay window and launcher window
- `mesmerglass/qss.py` — theme
- `mesmerglass/app.py` — entrypoint (creates QApplication)

Edit a single module and rerun `python run.py` for quick iteration.

