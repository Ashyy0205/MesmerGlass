"""Generate Android launcher icons from the MesmerGlass ICO asset.

Usage:
    python scripts/generate_mesmervisor_icons.py

Outputs PNGs for ic_launcher and ic_launcher_round across all standard
mipmap densities under the Android client project.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICO_PATH = PROJECT_ROOT / "mesmerglass_aperture_solar.ico"
RES_DIR = PROJECT_ROOT / "mesmerglass" / "vr" / "android-client" / "app" / "src" / "main" / "res"

DENSITIES: dict[str, int] = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}
ICON_NAMES = ("ic_launcher", "ic_launcher_round")


def main() -> None:
    if not ICO_PATH.exists():
        raise FileNotFoundError(f"ICO not found: {ICO_PATH}")

    base = Image.open(ICO_PATH).copy()

    for density, size in DENSITIES.items():
        target_dir = RES_DIR / f"mipmap-{density}"
        target_dir.mkdir(parents=True, exist_ok=True)

        for name in ICON_NAMES:
            out_path = target_dir / f"{name}.png"
            img = base.resize((size, size), Image.Resampling.LANCZOS)
            img.save(out_path, format="PNG")
            print(f"Wrote {out_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
