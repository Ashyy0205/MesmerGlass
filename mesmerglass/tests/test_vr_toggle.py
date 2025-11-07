import pytest

from mesmerglass.cli import build_parser


def test_run_vr_flags_parse():
    parser = build_parser()
    args = parser.parse_args(["run", "--vr"])  # should parse without error
    assert getattr(args, "vr", False) is True
    assert getattr(args, "vr_mock", False) is False

    args2 = parser.parse_args(["run", "--vr", "--vr-mock"])  # both flags
    assert getattr(args2, "vr", False) is True
    assert getattr(args2, "vr_mock", False) is True
