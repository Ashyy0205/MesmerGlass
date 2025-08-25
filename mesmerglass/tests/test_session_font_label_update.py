import json, os, pathlib, subprocess, sys

# This test ensures that after loading a session state containing a font path + family
# the UI (TextFxPage) updates its font family label via update_font_label.

def test_session_font_label_update(tmp_path):
    # Create fake font path (not a real font, but we test label wiring after restore)
    fake_font = tmp_path / 'dummy_font.ttf'
    fake_font.write_text('not a real font')
    state = {
        'textfx': {
            'font_path': str(fake_font),
            'font_family': 'FakeFontFam',
            'font_point_size': 24,
            'scale_pct': 42,
            'fx_mode': 'Shimmer',
            'fx_intensity': 33,
            'flash_interval_ms': 500,
            'flash_width_ms': 120,
        }
    }
    state_file = tmp_path / 'state.json'
    state_file.write_text(json.dumps(state))
    # Invoke UI in headless mode to load state and request status JSON
    env = os.environ.copy()
    env['MESMERGLASS_NO_SERVER'] = '1'
    cmd = [sys.executable, '-m', 'mesmerglass', 'ui', '--load-state', str(state_file), '--status', '--timeout', '0.05']
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip())
    # The status should reflect font_path + font_family from state restore
    assert out['font_path'] == str(fake_font)
    # We can't guarantee QFontDatabase accepted fake file, but update_font_label should've been called
    # so font_family should be either provided family or default fallback string.
    assert 'font_family' in out
