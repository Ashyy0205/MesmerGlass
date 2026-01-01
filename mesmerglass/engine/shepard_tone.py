from __future__ import annotations

import numpy as np


_SHEPARD_CACHE: dict[tuple[int, float, str, float, int, float], np.ndarray] = {}


def generate_shepard_tone_int16_stereo(
    *,
    duration_s: float = 60.0,
    sample_rate: int = 44100,
    direction: str = "ascending",
    f_min_hz: float = 55.0,
    octaves: int = 6,
    fade_s: float = 0.05,
    peak: float = 0.18,
) -> np.ndarray:
    """Generate a stereo int16 Shepard tone buffer.

    This is intended as a quiet, looping bed. It uses multiple octave-spaced
    partials with a Gaussian amplitude envelope in log-frequency space.

    Returns:
        numpy int16 array shaped (n_samples, 2)
    """

    duration_s = float(max(1.0, duration_s))
    sample_rate = int(max(8000, sample_rate))
    octaves = int(max(1, octaves))

    dir_norm = (direction or "ascending").strip().lower()
    if dir_norm.startswith("desc") or dir_norm in {"down", "decreasing"}:
        dir_norm = "descending"
    else:
        dir_norm = "ascending"

    # Cache generated PCM to avoid regenerating every cue.
    cache_key = (sample_rate, float(duration_s), dir_norm, float(f_min_hz), int(octaves), float(peak))
    cached = _SHEPARD_CACHE.get(cache_key)
    if cached is not None:
        return cached

    n = int(round(duration_s * sample_rate))

    # We generate in chunks to keep peak memory low even for long buffers.
    sig = np.zeros(n, dtype=np.float32)
    center = float(octaves) / 2.0
    sigma = max(0.35, float(octaves) / 6.0)
    two_pi_over_sr = (2.0 * np.pi) / float(sample_rate)
    octaves_f = float(octaves)
    f_min = float(f_min_hz)

    # Track running phase for each partial across chunks.
    phase0 = np.zeros(octaves, dtype=np.float64)
    chunk = 65536

    sign = -1.0 if dir_norm == "descending" else 1.0
    for start in range(0, n, chunk):
        end = min(n, start + chunk)
        idx = np.arange(start, end, dtype=np.float64)
        t = idx / float(sample_rate)

        # Sweep over exactly `octaves` during the buffer; repeats each duration.
        sweep = sign * ((t / duration_s) * octaves_f)

        # Accumulate partials
        acc = np.zeros(end - start, dtype=np.float64)
        for k in range(octaves):
            p = (float(k) + sweep) % octaves_f
            freqs = f_min * (2.0 ** p)
            env = np.exp(-0.5 * ((p - center) / sigma) ** 2)
            dphi = two_pi_over_sr * freqs
            phase = phase0[k] + np.cumsum(dphi)
            phase0[k] = float(phase[-1])
            acc += np.sin(phase) * env

        sig[start:end] = acc.astype(np.float32)

    # Normalize then apply a small fade on both ends to reduce loop clicks.
    peak = float(max(0.01, min(0.95, peak)))
    denom = float(np.max(np.abs(sig)) + 1e-9)
    sig = (sig.astype(np.float64) / denom) * peak

    fade_n = int(round(float(fade_s) * sample_rate))
    fade_n = int(max(0, min(fade_n, n // 4)))
    if fade_n > 0:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, fade_n, dtype=np.float64))
        sig[:fade_n] *= ramp
        sig[-fade_n:] *= ramp[::-1]

    stereo = np.stack([sig, sig], axis=1)
    pcm = np.clip(stereo * 32767.0, -32768.0, 32767.0).astype(np.int16)
    _SHEPARD_CACHE[cache_key] = pcm
    return pcm
