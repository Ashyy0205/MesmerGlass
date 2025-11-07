import importlib.util
from pathlib import Path


def _import_visual_mode_creator(repo_root: Path):
    vmc_path = repo_root / 'scripts' / 'visual_mode_creator.py'
    assert vmc_path.is_file(), f"visual_mode_creator.py not found at {vmc_path}"
    spec = importlib.util.spec_from_file_location("visual_mode_creator", str(vmc_path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_media_root_exists():
    # Walk up from this test file until we find repo root (contains scripts/ folder)
    here = Path(__file__).resolve()
    candidate = here.parent
    while candidate.parent != candidate:
        if (candidate / 'scripts' / 'visual_mode_creator.py').is_file():
            repo_root = candidate
            break
        candidate = candidate.parent
    else:
        raise AssertionError("Could not locate repo root with scripts/visual_mode_creator.py")

    vmc = _import_visual_mode_creator(repo_root)

    media_root = getattr(vmc, 'PROJECT_ROOT', repo_root) / 'MEDIA'
    assert media_root.is_dir(), f"MEDIA directory not found at {media_root}"

    # Optional: sanity check expected subfolders
    assert (media_root / 'Images').is_dir(), "MEDIA/Images folder missing"
    assert (media_root / 'Videos').is_dir(), "MEDIA/Videos folder missing"
