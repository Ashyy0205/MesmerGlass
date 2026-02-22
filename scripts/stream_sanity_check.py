"""Sanity-check per-channel streaming.

Generates a small stereo WAV tone and streams it through AudioEngine.stream_channel,
printing mixer/channel state as it runs.

Usage:
  python scripts/stream_sanity_check.py
"""

from __future__ import annotations

import math
import sys
import time
import wave
from pathlib import Path

import numpy as np
import pygame

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mesmerglass.engine.audio import AudioEngine


def _write_test_wav(
    path: Path,
    *,
    seconds: float = 2.0,
    rate: int = 44100,
    channels: int = 2,
) -> None:
    frames = int(rate * float(seconds))
    t = np.arange(frames, dtype=np.float32) / float(rate)
    sig = (0.2 * np.sin(2.0 * math.pi * 440.0 * t)).astype(np.float32)
    mono16 = (sig * 32767.0).astype(np.int16)
    if int(channels) == 1:
        pcm = mono16.reshape(-1, 1)
    else:
        pcm = np.stack([mono16, mono16], axis=1)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1 if int(channels) == 1 else 2)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())


def main() -> int:
    wav_rate = 44100
    wav_channels = 2
    try:
        if len(sys.argv) >= 2:
            wav_rate = int(float(sys.argv[1]))
    except Exception:
        wav_rate = 44100

    if len(sys.argv) >= 3:
        arg = str(sys.argv[2]).strip().lower()
        if arg in ("mono", "1"):
            wav_channels = 1
        elif arg in ("stereo", "2"):
            wav_channels = 2

    out_path = Path("build") / "stream_test_tone.wav"
    _write_test_wav(out_path, rate=wav_rate, channels=wav_channels)

    eng = AudioEngine(num_channels=3)
    print("mixer init:", pygame.mixer.get_init())
    print("wav rate:", wav_rate)
    print("wav channels:", wav_channels)

    ok = eng.stream_channel(0, str(out_path), volume=0.7, fade_ms=0, loop=True)
    print("stream_channel ok:", ok)

    ch = pygame.mixer.Channel(0)
    for i in range(16):
        time.sleep(0.25)
        try:
            print(
                f"t={(i + 1) * 0.25:.2f}s busy={ch.get_busy()} queued={ch.get_queue() is not None} vol={ch.get_volume():.3f}"
            )
        except Exception as exc:
            print("channel query error:", exc)

    eng.stop_channel(0)
    try:
        print("after stop busy:", ch.get_busy())
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
