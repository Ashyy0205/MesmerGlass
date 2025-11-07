import ctypes
import types

from mesmerglass.vr.vr_bridge import VrBridge


class Dummy:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_as_xr_handle_int():
    b = VrBridge(enabled=False)
    assert b._as_xr_handle(123) == 123


def test_as_xr_handle_attr_handle():
    b = VrBridge(enabled=False)
    obj = Dummy(handle=456)
    assert b._as_xr_handle(obj) == 456


def test_as_xr_handle_attr_value():
    b = VrBridge(enabled=False)
    obj = Dummy(value=789)
    assert b._as_xr_handle(obj) == 789


def test_as_xr_handle_ctypes_void_p():
    b = VrBridge(enabled=False)
    ptr = ctypes.c_void_p(0xDEADBEEF)
    assert b._as_xr_handle(ptr) == 0xDEADBEEF


def test_as_xr_handle_missing_returns_none():
    b = VrBridge(enabled=False)
    obj = Dummy()
    assert b._as_xr_handle(obj) is None


def test_as_xr_handle_ctypes_pointer_uint64():
    b = VrBridge(enabled=False)
    v = ctypes.c_uint64(0x123456789ABCDEF0)
    ptr = ctypes.pointer(v)
    assert b._as_xr_handle(ptr) == 0x123456789ABCDEF0


def test_as_xr_handle_dummy_with_contents():
    b = VrBridge(enabled=False)
    class WithContents:
        pass
    o = WithContents()
    # Emulate a binding object exposing `.contents` that itself has a `.value`
    o.contents = ctypes.c_uint64(0xCAFEBABEDEADC0DE)
    assert b._as_xr_handle(o) == 0xCAFEBABEDEADC0DE
