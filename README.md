# Mesmer Glass

  

**Mesmer Glass** is a desktop overlay that blends hypnotic visuals and timed text prompts with optional, *consensual* device feedback. It runs above everything on your screen, stays click‑through, and can span multiple displays—so you can keep using your computer while it runs a session in the background.

  

---

  

## Install (Windows 10/11)

  

### 1) Get Python

- Install **Python 3.12 (64‑bit)** from [python.org](https://www.python.org/downloads/).  

  ✅ During install, **check “Add python.exe to PATH.”**  

  *If you already have the Microsoft Store Python, prefer using the `py` launcher in the steps below.*

  

### 2) Prepare a folder

Put `MesmerGlass.py` (or your current script) in a new folder, e.g. `C:\MesmerGlass\`.

  

### 3) Create a virtual environment

Open **Windows PowerShell** in that folder and run:

```powershell

py -3.12 -m venv .venv

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip wheel

```

  

### 4) Install dependencies

Either install from the provided requirements file:

```powershell

pip install -r requirements.txt

```

…or install packages one by one:

```powershell

pip install pyqt6 opencv-python av pygame websockets numpy

```

  

> If `pip` warns about not being on PATH, use the `py -3.12 -m pip install …` form instead.

  

### 5) (Optional) Set up Intiface for device control

- Install **Intiface Central**.

- Open it and click **Start Server** (default endpoint `ws://127.0.0.1:12345`).

- Open **Device Manager → Start Scanning** and pair your toy. Ensure it shows as **Connected**.

- Keep Intiface running while you use Mesmer Glass.

  

### 6) Run Mesmer Glass

From the same PowerShell (with the venv active):

```powershell

python MesmerGlass.py

```


  

---

  

## What it does (current features)

  

- **Click‑through glass overlay** (always on top, non‑interactive).

- **Primary & secondary video layers** with independent opacity.

- **Text flash** centered on screen, with **alpha = primary video opacity + 2%** (clamped) and **Screen** blend so white stays bright at low opacity.

- **Hypnotic text effects** (Breath + Sway, Shimmer, Tunnel, Subtle) with intensity control and auto-fit sizing.

- **Custom fonts & colors** (add your own TTF/OTF).

- **Dual audio tracks** with individual volume (looped).

- **Optional device sync** via **Intiface/Buttplug v3 over WebSocket**:

  - **Buzz on Flash:** every text flash triggers a pulse (duration = Flash Width).

  - **Random bursts:** occasional micro-patterns (hit, wave, edge) within your min/max spacing, peak, and duration.

- **Multi-display launch**—pick which screens to use.

- **Resilient connection**—background WS loop with simple reconnects; zeroes device output on exit.

  

---

  

## Terminology

  

- **Flash Interval (ms):** how often the text appears.

- **Flash Width (ms):** how long the text stays visible *per flash*. When **Buzz on Flash** is enabled, Flash Width = **pulse duration**.

  

---

  

## Quick start (how to use)

  

1. **Select videos**

   - **Primary video** (required) and optional **Secondary** overlay video.

   - Set **Primary Opacity** and **Secondary Opacity** to taste.

  

2. **Configure text**

   - Enter your **Message**.

   - Choose **Font** (add TTF/OTF if you want), **Text Size**, **Color**.

   - Pick an **FX preset** and set **Intensity**.

   - Enable **Flash** and set **Interval** (how often) and **Flash Width** (how long it shows).  

     *Flash Width also sets the device pulse duration when Buzz on Flash is enabled.*

  

3. **Audio (optional)**

   - Load **Audio 1** and **Audio 2**, set volumes. Both loop.

  

4. **Device sync (optional)**

   - Enable **Buzz on Flash** and set **Intensity** (strength of the pulse).

   - Toggle **Random Bursts**, then tune **min/max delay**, **max intensity**, and **max duration**.

   - Use **Test Burst** to verify output.

  

5. **Displays**

   - Tick the monitors where you want the overlay to appear.

  

6. **Launch**

   - Click **Launch Overlay**. The overlays will full‑screen on the selected monitors, the audio will start, and the device engine will connect.  

   - Close the main window to stop everything; outputs are zeroed on exit.

  

---

  

## Troubleshooting

  

**`pip` errors / cannot import**  

- Ensure your virtual environment is **activated** (`.\.venv\Scripts\Activate.ps1`).  

- Use the launcher explicitly: `py -3.12 -m pip install ...`  

- Upgrade pip/wheel: `python -m pip install -U pip wheel`

  

**`av` install fails**  

- Make sure you’re on **Python 3.10–3.12** (32‑bit builds are not recommended).  

- Try `pip install "av>=11,<12"`

  

**No devices found**  

- Ensure Intiface Central is **running** and the **Server** is started (`ws://127.0.0.1:12345`).  

- Pair your device in **Device Manager** and verify it shows as **Connected**.  

- Close vendor apps that might own the BLE connection.  

- Toggle device power/BLE and rescan.

  

**WS timeouts**  

- Avoid OS sleep/BT power‑saver during sessions. Restart the Intiface Server if the link stalls.

  

**Audio memory usage**  

- Large WAVs use more RAM with `pygame`. Prefer MP3/OGG for now. (Planned: switch to streaming audio backend.)

  

**Overlay not click‑through**  

- Rare GPU/Qt combos can misbehave. Run non‑admin, disable other overlays, and keep GPU drivers current. (Planned: Win32 layered/transparent fallback.)


---

  

## Credits

  

- **Buttplug/Intiface**, **PyQt6**, **OpenCV**, **PyAV**, **pygame**, **websockets**.

  

## License & privacy

  

- Runs locally; no cloud calls.  

- Use responsibly. Keep sessions consensual and within the law where you live.
