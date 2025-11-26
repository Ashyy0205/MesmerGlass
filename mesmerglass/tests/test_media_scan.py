from pathlib import Path

from mesmerglass.content.media_scan import scan_media_directory


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_scan_media_directory_handles_mixed_case_extensions(tmp_path):
    img_a = tmp_path / "Gallery" / "Summer" / "photo.JPG"
    img_b = tmp_path / "Gallery" / "RAW" / "portrait.PnG"
    video = tmp_path / "Clips" / "INTRO.MP4"
    other = tmp_path / "Docs" / "notes.txt"

    for target in (img_a, img_b, video, other):
        _touch(target)

    images, videos = scan_media_directory(tmp_path)

    assert set(images) == {str(img_a.resolve()), str(img_b.resolve())}
    assert set(videos) == {str(video.resolve())}


def test_scan_media_directory_missing_root_returns_empty(tmp_path):
    missing = tmp_path / "does" / "not" / "exist"
    images, videos = scan_media_directory(missing)
    assert images == []
    assert videos == []
