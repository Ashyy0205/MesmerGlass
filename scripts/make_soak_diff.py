from pathlib import Path
import argparse
import difflib

OLD_PATH = Path("mesmerglass/sessions/test-soak.session.json")
NEW_PATH = Path("mesmerglass/sessions/test-soak.session.new.json")


def slice_lines(lines: list[str], start: int | None, end: int | None) -> list[str]:
    """Return a slice of the lines between the provided 1-based bounds."""
    if start is not None:
        start_idx = max(start - 1, 0)
    else:
        start_idx = 0
    end_idx = end if end is not None else None
    return lines[start_idx:end_idx]


def main() -> None:
    parser = argparse.ArgumentParser(description="Show diff between soak files")
    parser.add_argument("--start", type=int, default=None, help="1-based start line for diff slice")
    parser.add_argument("--end", type=int, default=None, help="1-based end line for diff slice")
    args = parser.parse_args()

    old_lines = OLD_PATH.read_text().splitlines()
    new_lines = NEW_PATH.read_text().splitlines()

    old_slice = slice_lines(old_lines, args.start, args.end)
    new_slice = slice_lines(new_lines, args.start, args.end)

    diff = difflib.unified_diff(
        old_slice,
        new_slice,
        fromfile=str(OLD_PATH),
        tofile=str(NEW_PATH),
        lineterm="",
    )
    print("\n".join(diff))


if __name__ == "__main__":
    main()
