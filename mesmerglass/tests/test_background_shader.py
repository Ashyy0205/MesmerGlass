import re

# Static test: ensure background FS shader does not redeclare aspect variables

def test_background_shader_no_duplicate_aspect_decls():
    from mesmerglass.mesmerloom.window_compositor import LoomWindowCompositor
    src = LoomWindowCompositor._background_fs_source()
    # Count occurrences of variable declarations
    win_decl = len(re.findall(r"\bfloat\s+windowAspect\s*=", src))
    img_decl = len(re.findall(r"\bfloat\s+imageAspect\s*=", src))
    assert win_decl == 1, f"windowAspect declared {win_decl} times"
    assert img_decl == 1, f"imageAspect declared {img_decl} times"
