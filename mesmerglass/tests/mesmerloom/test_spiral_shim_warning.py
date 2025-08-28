import warnings

def test_spiral_engine_shim_warning():
    import sys
    # Ensure fresh import so the module-level DeprecationWarning is emitted
    sys.modules.pop("mesmerglass.engine.spiral", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import mesmerglass.engine.spiral  # noqa: F401
        dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert dep, "No DeprecationWarning emitted"
        assert any("deprecated; use mesmerglass.mesmerloom.spiral" in str(w.message) for w in dep)
        from mesmerglass.engine.spiral import SpiralDirector as LegacyDirector
        from mesmerglass.mesmerloom.spiral import SpiralDirector as NewDirector
        assert LegacyDirector.__name__ == NewDirector.__name__
