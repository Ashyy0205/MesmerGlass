import math
from mesmerglass.engine.spiral import SpiralDirector, SpiralConfig

def test_spiral_director_basic_evolution():
    sd = SpiralDirector(SpiralConfig(intensity=0.4), seed=7)
    u0 = sd.uniforms()
    arms0 = u0['uArms']
    assert isinstance(arms0, (int, float)) and 2 <= arms0 <= 8
    for _ in range(120):
        sd.update(1/60)
    u1 = sd.uniforms()
    # Values should evolve slightly but remain clamped
    bw0 = u0['uBarWidth']; bw1 = u1['uBarWidth']
    assert isinstance(bw1, (int, float))
    if isinstance(bw0, (int, float)):
        assert abs(bw1 - bw0) < 0.1
    op1 = u1['uOpacity']; assert isinstance(op1, (int,float)) and 0.3 <= op1 <= 1.0
    sp1 = u1['uSpeedCPS']; assert isinstance(sp1, (int,float)) and -sd.MAX_PHASE_SPEED <= sp1 <= sd.MAX_PHASE_SPEED
    assert sd.BAR_WIDTH_MIN <= bw1 <= sd.BAR_WIDTH_MAX
    ct1 = u1['uContrast']; assert isinstance(ct1,(int,float)) and sd.CONTRAST_MIN <= ct1 <= sd.CONTRAST_MAX

def test_intensity_scaling_changes_speed():
    sd = SpiralDirector()
    base_speed = sd.cfg.speed_base_cps
    sd.set_intensity(0.9, abrupt=True)
    assert sd.cfg.speed_base_cps > base_speed

# New MesmerLoom SpiralDirector (Phase 2) tests
try:
    from mesmerglass.mesmerloom.spiral import SpiralDirector as LoomDirector
except Exception:  # pragma: no cover
    LoomDirector = None  # type: ignore

REQUIRED_KEYS_NEW = {
    'uPhase','uBaseSpeed','uEffectiveSpeed','uBarWidth','uTwist','uSpiralOpacity',
    'uContrast','uVignette','uChromaticShift','uFlipWaveRadius','uFlipState','uIntensity','uSafetyClamped'
}

def test_mesmerloom_export_uniform_keys():
    if LoomDirector is None:
        return
    d = LoomDirector(seed=3)
    keys = set(d.export_uniforms().keys())
    missing = REQUIRED_KEYS_NEW - keys
    assert not missing, f"Missing new loom keys: {missing}"

def test_mesmerloom_uniform_values_progress():
    if LoomDirector is None:
        return
    d = LoomDirector(seed=4)
    d.set_intensity(0.6)
    p0 = d.state.phase
    for _ in range(90):
        d.update(1/60)
    uni = d.export_uniforms()
    assert uni['uPhase'] >= p0
    assert 0.0 <= uni['uIntensity'] <= 1.0
    assert 0.0 <= uni['uBarWidth'] <= 1.0
    assert 0.0 <= uni['uSpiralOpacity'] <= 1.0
