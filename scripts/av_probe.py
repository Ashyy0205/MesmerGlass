"""Probe PyAV decoding in this environment.

Creates a small WAV tone and then attempts to decode it using PyAV, printing
stream, packet, and frame counts.

Usage:
  python scripts/av_probe.py
"""

from __future__ import annotations

import math
import sys
import wave
import threading
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _write_test_wav(path: Path, *, seconds: float = 1.0, rate: int = 44100) -> None:
    frames = int(rate * float(seconds))
    t = np.arange(frames, dtype=np.float32) / float(rate)
    sig = (0.2 * np.sin(2.0 * math.pi * 440.0 * t)).astype(np.float32)
    mono16 = (sig * 32767.0).astype(np.int16)
    stereo = np.stack([mono16, mono16], axis=1)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(stereo.tobytes())


def main() -> int:
    out_path = Path("build") / "av_probe_tone.wav"
    _write_test_wav(out_path)
    print("file:", out_path.resolve())
    print("bytes:", out_path.stat().st_size)

    try:
        import av  # type: ignore
    except Exception as exc:
        print("PyAV import failed:", exc)
        return 2

    container = av.open(str(out_path))
    print("format:", getattr(container.format, "name", None))
    print("duration:", getattr(container, "duration", None))

    streams = list(container.streams)
    print("streams:", [(s.index, getattr(s, "type", None), getattr(getattr(s, "codec_context", None), "name", None)) for s in streams])

    # Decode frames (main thread)
    frames = 0
    samples = 0
    try:
        for frame in container.decode(audio=0):
            frames += 1
            try:
                samples += int(getattr(frame, "samples", 0) or 0)
            except Exception:
                pass
            if frames >= 10:
                break
        print("decode(audio=0): frames", frames, "samples", samples)
    except Exception as exc:
        print("decode(audio=0) error:", exc)

    # Decode frames (background thread)
    thread_result: dict[str, object] = {"frames": 0, "samples": 0, "error": None}

    def _thread_decode() -> None:
        try:
            c = av.open(str(out_path))
            f = 0
            s = 0
            for fr in c.decode(audio=0):
                f += 1
                try:
                    s += int(getattr(fr, "samples", 0) or 0)
                except Exception:
                    pass
                if f >= 10:
                    break
            try:
                c.close()
            except Exception:
                pass
            thread_result["frames"] = f
            thread_result["samples"] = s
        except Exception as exc:
            thread_result["error"] = str(exc)

    th = threading.Thread(target=_thread_decode, name="av-probe-thread")
    th.start()
    th.join(timeout=5.0)
    print(
        "thread decode:",
        "frames",
        thread_result.get("frames"),
        "samples",
        thread_result.get("samples"),
        "error",
        thread_result.get("error"),
    )

    # Demux packets
    container.close()
    container = av.open(str(out_path))
    pkt_count = 0
    try:
        for pkt in container.demux(audio=0):
            pkt_count += 1
            if pkt_count >= 10:
                break
        print("demux(audio=0): packets", pkt_count)
    except Exception as exc:
        print("demux(audio=0) error:", exc)
    finally:
        try:
            container.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
