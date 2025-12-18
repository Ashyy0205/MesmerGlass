"""Generate a soak-test session that exercises Test Media.

Creates a single session file containing three cuelists:
- 5 minutes
- 15 minutes
- 30 minutes

Each cue is short (default 4s) and advances through available audio files to
maximize coverage within the requested durations.

Usage (PowerShell):
  C:/Users/Ash/Desktop/MesmerGlass/.venv/Scripts/python.exe scripts/generate_soak_session.py

Optional:
    --test-media "C:/Users/Ash/Desktop/Test Media"
  --out mesmerglass/sessions/soak_test_test_media.session.json
  --cue-seconds 4
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import random
from typing import Iterable, Sequence


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
FONT_EXTS = {".ttf", ".otf"}


@dataclass(frozen=True)
class MediaInventory:
    images: list[Path]
    videos: list[Path]
    audio: list[Path]
    fonts: list[Path]


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (p for p in root.rglob("*") if p.is_file())


def scan_inventory(
    root: Path,
    *,
    exclude_audio_dirs: Sequence[Path] | None = None,
) -> MediaInventory:
    images: list[Path] = []
    videos: list[Path] = []
    audio: list[Path] = []
    fonts: list[Path] = []

    exclude_audio_dirs = list(exclude_audio_dirs or [])

    def _is_excluded_audio(path: Path) -> bool:
        # Exclude by absolute prefix when possible.
        try:
            abs_path = path.resolve()
        except Exception:
            abs_path = path
        abs_path_str = str(abs_path).lower().rstrip("\\/")

        for ex in exclude_audio_dirs:
            try:
                abs_ex = ex.resolve()
            except Exception:
                abs_ex = ex
            abs_ex_str = str(abs_ex).lower().rstrip("\\/")
            if abs_path_str == abs_ex_str or abs_path_str.startswith(abs_ex_str + "\\"):
                return True

        # Also exclude by folder name for robustness.
        return any(part.lower() == "mixed-abdl-hypnosis" for part in path.parts)

    for p in _iter_files(root):
        suf = p.suffix.lower()
        if suf in IMAGE_EXTS:
            images.append(p)
        elif suf in VIDEO_EXTS:
            videos.append(p)
        elif suf in AUDIO_EXTS:
            if not _is_excluded_audio(p):
                audio.append(p)
        elif suf in FONT_EXTS:
            fonts.append(p)

    # Stable ordering for deterministic session files
    images.sort(key=lambda x: str(x).lower())
    videos.sort(key=lambda x: str(x).lower())
    audio.sort(key=lambda x: str(x).lower())
    fonts.sort(key=lambda x: str(x).lower())

    return MediaInventory(images=images, videos=videos, audio=audio, fonts=fonts)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _make_playback(
    *,
    name: str,
    spiral_type: str,
    rotation_speed: float,
    spiral_opacity: float,
    reverse: bool,
    arm_color: Sequence[float],
    gap_color: Sequence[float],
    media_mode: str,
    cycle_speed: int,
    bank_selections: Sequence[int],
    text_enabled: bool,
    zoom_mode: str,
    zoom_rate: float,
) -> dict:
    return {
        "version": "1.0",
        "name": name,
        "description": "Auto-generated soak playback",
        "spiral": {
            "type": spiral_type,
            "rotation_speed": float(rotation_speed),
            "opacity": float(spiral_opacity),
            "reverse": bool(reverse),
            "arm_color": [float(arm_color[0]), float(arm_color[1]), float(arm_color[2])],
            "gap_color": [float(gap_color[0]), float(gap_color[1]), float(gap_color[2])],
        },
        "media": {
            "mode": media_mode,
            "cycle_speed": int(cycle_speed),
            "fade_duration": 0.0,
            "use_theme_bank": True,
            "paths": [],
            "shuffle": False,
            "bank_selections": list(bank_selections),
        },
        "text": {
            "enabled": bool(text_enabled),
            "mode": "centered_sync",
            "opacity": 0.85,
            "use_theme_bank": True,
            "library": [],
            "sync_with_media": True,
            "manual_cycle_speed": int(cycle_speed),
            "color": [1.0, 1.0, 1.0],
            # CustomVisual supports this key (defaults True) and it helps
            # ensure we exercise the font bank.
            "use_font_bank": True,
        },
        "zoom": {"mode": zoom_mode, "rate": float(zoom_rate)},
        "accelerate": {
            "enabled": False,
            "duration": 30,
            "start_rotation_x": 4.0,
            "start_media_speed": 50.0,
            "start_zoom_rate": 0.2,
        },
    }


def _make_cue(
    *,
    name: str,
    duration_seconds: float,
    playback_pool: Sequence[dict],
    selection_mode: str,
    selection_interval_seconds: float | None,
    transition_in: dict,
    transition_out: dict,
    audio_tracks: Sequence[dict] | None,
    text_messages: Sequence[str] | None,
    vibrate_on_text_cycle: bool,
    vibration_intensity: float,
) -> dict:
    cue: dict = {
        "name": name,
        "duration_seconds": float(duration_seconds),
        "playback_pool": list(playback_pool),
        "selection_mode": selection_mode,
        "transition_in": dict(transition_in),
        "transition_out": dict(transition_out),
    }

    if selection_interval_seconds is not None:
        cue["selection_interval_seconds"] = float(selection_interval_seconds)

    if audio_tracks:
        cue["audio_tracks"] = list(audio_tracks)

    if text_messages is not None:
        cue["text_messages"] = list(text_messages)

    if vibrate_on_text_cycle:
        cue["vibrate_on_text_cycle"] = True
        cue["vibration_intensity"] = float(vibration_intensity)

    return cue


def _pb_entry(
    *,
    playback: str,
    weight: float,
    cue_seconds: float,
    min_s: float | None = None,
    max_s: float | None = None,
) -> dict:
    # Exercise pool constraints; keep them safe for short cues.
    if min_s is None:
        min_s = 1.0
    if max_s is None:
        max_s = float(cue_seconds)
    return {
        "playback": playback,
        "weight": float(weight),
        "min_duration_s": float(min_s),
        "max_duration_s": float(max_s),
    }


def _audio_track(*, path: Path, role: str, volume: float, loop: bool, fade_ms: int) -> dict:
    return {
        "file": str(path),
        "volume": float(volume),
        "loop": bool(loop),
        "fade_in_ms": int(fade_ms),
        "fade_out_ms": int(fade_ms),
        "role": role,
    }


def _make_cuelist(
    *,
    name: str,
    total_seconds: int,
    cue_seconds: int,
    playback_pool: Sequence[str],
    audio_files: Sequence[Path],
    audio_offset: int,
    rng: random.Random,
) -> tuple[dict, int]:
    # Build variable cue durations that sum exactly to total_seconds.
    # `cue_seconds` is treated as a *target average* used for weighting.
    target_avg = max(2, int(cue_seconds))
    allowed = [2, 3, 4, 5, 6, 8, 10, 12, 15]

    reachable = [False] * (total_seconds + 1)
    reachable[0] = True
    for s in range(1, total_seconds + 1):
        reachable[s] = any(reachable[s - d] for d in allowed if s - d >= 0)
    if not reachable[total_seconds]:
        raise ValueError(f"Cannot compose total_seconds={total_seconds} from allowed durations={allowed}")

    durations: list[int] = []
    remaining = total_seconds
    while remaining > 0:
        candidates = [d for d in allowed if d <= remaining and reachable[remaining - d]]
        if not candidates:
            raise RuntimeError(f"Failed to compose remaining={remaining}")

        # Weight toward the target average, with additional variation by cuelist size.
        weights: list[float] = []
        for d in candidates:
            base = 1.0 / (1.0 + abs(d - target_avg))
            if total_seconds <= 300:
                base *= 1.25 if d <= 6 else 0.85
            elif total_seconds >= 1800:
                base *= 1.25 if d >= 4 else 0.9
            # Encourage more spread.
            if d in (2, 15):
                base *= 1.15
            weights.append(base)

        pick = rng.choices(candidates, weights=weights, k=1)[0]
        durations.append(pick)
        remaining -= pick

    cues: list[dict] = []
    audio_idx = audio_offset

    for i, cue_len in enumerate(durations):
        # Most cues use multiple playbacks to exercise pool switching.
        # Use deterministic rotation with a touch of weighted variety.
        if len(playback_pool) >= 4 and (i % 10) not in (0, 7):
            pool_size = 3 if (i % 3 != 0) else 4
        else:
            pool_size = 2 if len(playback_pool) >= 2 else 1

        # Choose playbacks by rotating window to keep coverage even.
        start = i % max(1, len(playback_pool))
        chosen = [playback_pool[(start + j) % len(playback_pool)] for j in range(pool_size)]

        # Weights: mostly even, occasionally biased to test weighted selection.
        entries: list[dict] = []
        for j, pb in enumerate(chosen):
            weight = 1.0
            if j == 0 and (i % 8 == 0):
                weight = 3.0
            elif j == 1 and (i % 11 == 0):
                weight = 2.0
            entries.append(_pb_entry(playback=pb, weight=weight, cue_seconds=float(cue_len)))

        # Selection: prefer switching modes to stress the runner.
        if pool_size >= 3 and (i % 4 != 0):
            selection_mode = "on_media_cycle"
            selection_interval_seconds = None
        elif pool_size >= 2 and (i % 6 == 0):
            selection_mode = "on_timed_interval"
            # Ensure the interval is small enough to actually trigger within the cue.
            max_interval = max(2.0, float(cue_len) - 1.0)
            selection_interval_seconds = float(rng.choice([2.0, 3.0, 4.0]))
            if selection_interval_seconds > max_interval:
                selection_interval_seconds = max_interval
        else:
            selection_mode = "on_cue_start"
            selection_interval_seconds = None

        # Transitions: mostly none (fast), sometimes fade/interpolate.
        if i % 9 == 0:
            ms = 250 if cue_len <= 4 else 500
            transition_in = {"type": "fade", "duration_ms": ms}
            transition_out = {"type": "fade", "duration_ms": ms}
        elif i % 13 == 0:
            ms = 350 if cue_len <= 4 else 700
            transition_in = {"type": "interpolate", "duration_ms": ms}
            transition_out = {"type": "interpolate", "duration_ms": ms}
        else:
            transition_in = {"type": "none", "duration_ms": 0}
            transition_out = {"type": "none", "duration_ms": 0}

        # Audio: mix of 0/1/2 tracks to exercise roles and layering.
        tracks: list[dict] = []
        if audio_files and (i % 7 != 0):  # ~6/7 cues have audio
            hypno_path = audio_files[audio_idx % len(audio_files)]
            audio_idx += 1
            if (i % 5 == 0) and len(audio_files) >= 2:
                bg_path = audio_files[audio_idx % len(audio_files)]
                audio_idx += 1
                if bg_path == hypno_path and len(audio_files) > 2:
                    bg_path = audio_files[audio_idx % len(audio_files)]
                    audio_idx += 1
                fade_a = 60 if cue_len <= 4 else 120
                fade_b = 90 if cue_len <= 4 else 180
                tracks.append(_audio_track(path=hypno_path, role="hypno", volume=0.85, loop=False, fade_ms=fade_a))
                tracks.append(_audio_track(path=bg_path, role="background", volume=0.55, loop=(i % 10 == 0), fade_ms=fade_b))
            else:
                role = "hypno" if (i % 2 == 0) else "background"
                vol = 0.85 if role == "hypno" else 0.60
                fade = 50 if cue_len <= 3 else (70 if cue_len <= 6 else 120)
                tracks.append(_audio_track(path=hypno_path, role=role, volume=vol, loop=(role == "background" and (i % 12 == 0)), fade_ms=fade))

        # Cue-level text override occasionally.
        text_messages = None
        if i % 5 == 0:
            bank = [
                "Focus on my voice",
                "Breathe and let go",
                "Deeper with every breath",
                "Relax your mind",
                "Drop into calm",
                "Eyes heavy",
                "Thoughts drifting",
                "Obey the rhythm",
                "Sinking now",
                "Stillness",
                "Blank",
                "Follow",
                "Listen",
                "Release control",
                "Safe and calm",
                "Quiet",
            ]
            n = 1 if cue_len <= 3 else (2 if cue_len <= 6 else 3)
            if i % 20 == 0:
                n = 4
            text_messages = rng.sample(bank, k=min(n, len(bank)))

        # Vibration tests occasionally.
        vibrate_on_text_cycle = (i % 23 == 0)
        vibration_intensity = 0.35 if (i % 46 == 0) else 0.7

        cues.append(
            _make_cue(
                name=f"{name} Cue {i+1:03d}",
                duration_seconds=float(cue_len),
                playback_pool=entries,
                selection_mode=selection_mode,
                selection_interval_seconds=selection_interval_seconds,
                transition_in=transition_in,
                transition_out=transition_out,
                audio_tracks=tracks,
                text_messages=text_messages,
                vibrate_on_text_cycle=vibrate_on_text_cycle,
                vibration_intensity=vibration_intensity,
            )
        )

    cuelist = {
        "name": name,
        "description": f"Auto-generated soak cuelist ({total_seconds}s)",
        "version": "1.0",
        "author": "",
        "loop_mode": "once",
        "transition_mode": "snap",
        "transition_duration_ms": 0.0,
        "cues": cues,
        "metadata": {
            "target_seconds": int(total_seconds),
            "cue_seconds_target": int(cue_seconds),
            "cues_total": int(len(cues)),
            "cue_duration_min": int(min(durations) if durations else 0),
            "cue_duration_max": int(max(durations) if durations else 0),
        },
    }

    return cuelist, audio_idx


def _build_playbacks(*, bank_images: int, bank_videos: int, bank_both: int, rng: random.Random) -> dict:
    # Create a richer pool of playbacks to exercise more rendering/config paths.
    spiral_types = ["linear", "logarithmic", "inverse", "sqrt"]
    zoom_modes = ["none", "linear", "exponential", "pulse"]
    media_modes = [
        ("images", [bank_images]),
        ("videos", [bank_videos]),
        ("both", [bank_both]),
        ("none", [bank_images]),
    ]

    playbacks: dict[str, dict] = {}
    count = 0

    color_palette = [
        (1.0, 1.0, 1.0),
        (1.0, 0.2, 0.8),
        (0.2, 1.0, 0.8),
        (0.2, 0.6, 1.0),
        (1.0, 0.6, 0.2),
        (0.9, 0.9, 0.2),
    ]

    # Deterministic but varied combinations.
    for media_mode, selections in media_modes:
        for spiral_type in spiral_types:
            for zoom_mode in zoom_modes:
                # Keep the set reasonably sized; prioritize combos that matter.
                if media_mode == "none" and zoom_mode in ("pulse",):
                    continue
                if media_mode == "videos" and zoom_mode == "none":
                    continue
                count += 1
                key = f"soak_pb_{count:02d}"
                cycle_speed = 85 if (count % 3 != 0) else 45
                text_enabled = (count % 5 != 0)
                reverse = bool(count % 2)
                rotation_speed = 25.0 + (count % 8) * 7.5
                spiral_opacity = 0.22 + (count % 6) * 0.06
                zoom_rate = 0.0 if zoom_mode == "none" else (0.12 + (count % 4) * 0.05)

                arm = color_palette[(count + 1) % len(color_palette)]
                gap = (0.0, 0.0, 0.0) if (count % 4 != 0) else color_palette[count % len(color_palette)]

                pb = _make_playback(
                    name=f"Soak {media_mode}/{spiral_type}/{zoom_mode}",
                    spiral_type=spiral_type,
                    rotation_speed=rotation_speed,
                    spiral_opacity=min(0.85, max(0.05, spiral_opacity)),
                    reverse=reverse,
                    arm_color=arm,
                    gap_color=gap,
                    media_mode=media_mode,
                    cycle_speed=cycle_speed,
                    bank_selections=selections,
                    text_enabled=text_enabled,
                    zoom_mode=zoom_mode,
                    zoom_rate=zoom_rate,
                )

                # Occasionally enable accelerate to hit that path.
                if count % 9 == 0:
                    pb["accelerate"]["enabled"] = True
                    pb["accelerate"]["duration"] = int(rng.choice([15, 30, 45]))

                # Occasionally desync text timing to exercise manual mode.
                if count % 7 == 0 and pb.get("text", {}).get("enabled"):
                    pb["text"]["sync_with_media"] = False
                    pb["text"]["manual_cycle_speed"] = int(rng.choice([35, 50, 70]))

                playbacks[key] = pb

                # Cap to avoid a gigantic session file.
                if count >= 24:
                    return playbacks

    return playbacks


def build_session(*, test_media: Path, cue_seconds: int, seed: int) -> dict:
    excluded = [test_media / "Audio" / "Mixed-ABDL-Hypnosis"]
    inv = scan_inventory(test_media, exclude_audio_dirs=excluded)

    rng = random.Random(int(seed))

    media_dir = test_media / "Image&Video"
    fonts_dir = test_media / "Fonts"

    media_bank = [
        {"name": "Test Media Images", "path": str(media_dir), "type": "images"},
        {"name": "Test Media Videos", "path": str(media_dir), "type": "videos"},
        {"name": "Test Media Both", "path": str(media_dir), "type": "both"},
        {"name": "Test Media Fonts", "path": str(fonts_dir), "type": "fonts"},
    ]

    playbacks = _build_playbacks(bank_images=0, bank_videos=1, bank_both=2, rng=rng)
    playback_pool = list(playbacks.keys())

    cuelists: dict[str, dict] = {}
    audio_offset = 0

    cuelist_5, audio_offset = _make_cuelist(
        name="Soak 5min",
        total_seconds=300,
        cue_seconds=cue_seconds,
        playback_pool=playback_pool,
        audio_files=inv.audio,
        audio_offset=audio_offset,
        rng=rng,
    )
    cuelists["soak_5min"] = cuelist_5

    cuelist_15, audio_offset = _make_cuelist(
        name="Soak 15min",
        total_seconds=900,
        cue_seconds=cue_seconds,
        playback_pool=playback_pool,
        audio_files=inv.audio,
        audio_offset=audio_offset,
        rng=rng,
    )
    # Exercise cuelist-level transition mode too.
    cuelist_15["transition_mode"] = "fade"
    cuelist_15["transition_duration_ms"] = 1200.0
    cuelists["soak_15min"] = cuelist_15

    cuelist_30, audio_offset = _make_cuelist(
        name="Soak 30min",
        total_seconds=1800,
        cue_seconds=cue_seconds,
        playback_pool=playback_pool,
        audio_files=inv.audio,
        audio_offset=audio_offset,
        rng=rng,
    )
    cuelists["soak_30min"] = cuelist_30

    created = _now_iso()

    session = {
        "version": "1.0",
        "metadata": {
            "name": "Soak Test (Test Media)",
            "description": "Auto-generated soak session using C:/Users/Ash/Desktop/Test Media",
            "created": created,
            "modified": created,
            "author": "",
            "tags": ["soak", "test-media"],
        },
        "playbacks": playbacks,
        "cuelists": cuelists,
        "media_bank": media_bank,
        "runtime": {
            "notes": {
                "inventory": {
                    "images": len(inv.images),
                    "videos": len(inv.videos),
                    "audio": len(inv.audio),
                    "fonts": len(inv.fonts),
                    "test_media_root": str(test_media),
                },
                "cue_seconds": cue_seconds,
                "audio_coverage": {
                    "audio_files_total": len(inv.audio),
                },
                "seed": int(seed),
                "playbacks_total": len(playbacks),
                "excluded_audio_dirs": [str(p) for p in excluded],
            }
        },
    }

    return session


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a soak-test session JSON.")
    parser.add_argument(
        "--test-media",
        default=r"C:\Users\Ash\Desktop\Test Media",
        help="Path to the Test Media folder",
    )
    parser.add_argument(
        "--out",
        default=str(Path("mesmerglass") / "sessions" / "soak_test_test_media.session.json"),
        help="Output session file path (relative to repo root)",
    )
    parser.add_argument(
        "--cue-seconds",
        type=int,
        default=4,
        help="Cue duration in seconds (must divide 300, 900, 1800 evenly)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
        help="Deterministic RNG seed for playback/cue variation",
    )

    args = parser.parse_args(argv)

    cue_seconds = int(args.cue_seconds)
    if cue_seconds <= 0:
        raise SystemExit("--cue-seconds must be > 0")

    repo_root = Path(__file__).resolve().parents[1]
    test_media = Path(args.test_media)
    out_path = (repo_root / args.out).resolve()

    session = build_session(test_media=test_media, cue_seconds=cue_seconds, seed=int(args.seed))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(session, indent=2), encoding="utf-8")

    inv = session.get("runtime", {}).get("notes", {}).get("inventory", {})
    print(f"Wrote: {out_path}")
    print(
        "Inventory:",
        f"images={inv.get('images')}",
        f"videos={inv.get('videos')}",
        f"audio={inv.get('audio')}",
        f"fonts={inv.get('fonts')}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
