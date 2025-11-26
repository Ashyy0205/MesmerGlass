"""
Test script to verify ALL Phase 7 engine wiring is working correctly.

Usage:
    .\.venv\Scripts\python.exe test_engine_wiring.py

This script:
1. Creates MainApplication
2. Checks all engines are initialized
3. Checks engines are passed to tabs correctly
4. Checks SessionRunner receives engines
5. Verifies compositor activation works
"""

import sys
from PyQt6.QtWidgets import QApplication
from mesmerglass.ui.main_application import MainApplication

def test_engine_wiring():
    """Comprehensive engine wiring test."""
    print("\n" + "="*70)
    print("PHASE 7 ENGINE WIRING TEST")
    print("="*70)
    
    app = QApplication(sys.argv)
    window = MainApplication()
    
    # ===== TEST 1: MainApplication Engines =====
    print("\n[TEST 1] MainApplication Engine Initialization")
    print("-" * 70)
    
    engines = {
        "spiral_director": window.spiral_director,
        "compositor": window.compositor,
        "text_renderer": window.text_renderer,
        "text_director": window.text_director,
        "visual_director": window.visual_director,
        "audio_engine": window.audio_engine,
        "device_manager": window.device_manager,  # May be None
    }
    
    for name, engine in engines.items():
        status = "✅ OK" if engine is not None else "❌ NONE"
        print(f"  {name:20s}: {status}")
        if engine is not None:
            print(f"    - Type: {type(engine).__name__}")
    
    # ===== TEST 2: Engine Types and APIs =====
    print("\n[TEST 2] Engine Type Verification")
    print("-" * 70)
    
    # SpiralDirector
    if window.spiral_director:
        has_intensity = hasattr(window.spiral_director, 'set_intensity')
        print(f"  SpiralDirector.set_intensity: {'✅' if has_intensity else '❌'}")
    
    # Compositor
    if window.compositor:
        has_set_active = hasattr(window.compositor, 'set_active')
        compositor_type = type(window.compositor).__name__
        print(f"  Compositor type: {compositor_type}")
        print(f"  Compositor.set_active: {'✅' if has_set_active else '❌'}")
    
    # AudioEngine
    if window.audio_engine:
        has_channels = hasattr(window.audio_engine, 'num_channels')
        has_load = hasattr(window.audio_engine, 'load_channel')
        has_fade = hasattr(window.audio_engine, 'fade_in_and_play')
        print(f"  AudioEngine.num_channels: {'✅' if has_channels else '❌'}")
        print(f"  AudioEngine.load_channel: {'✅' if has_load else '❌'}")
        print(f"  AudioEngine.fade_in_and_play: {'✅' if has_fade else '❌'}")
        if has_channels:
            print(f"    - Channels: {window.audio_engine.num_channels}")
    
    # VisualDirector
    if window.visual_director:
        has_load = hasattr(window.visual_director, 'load_playback')
        has_register = hasattr(window.visual_director, 'register_cycle_callback')
        print(f"  VisualDirector.load_playback: {'✅' if has_load else '❌'}")
        print(f"  VisualDirector.register_cycle_callback: {'✅' if has_register else '❌'}")
    
    # ===== TEST 3: HomeTab Wiring =====
    print("\n[TEST 3] HomeTab Engine Access")
    print("-" * 70)
    
    home_tab = window.home_tab
    
    # Check HomeTab has reference to MainApplication
    has_main = hasattr(home_tab, 'main_window')
    print(f"  HomeTab.main_window: {'✅' if has_main else '❌'}")
    
    if has_main:
        # Verify HomeTab can access engines via parent
        can_access_visual = hasattr(home_tab.main_window, 'visual_director')
        can_access_audio = hasattr(home_tab.main_window, 'audio_engine')
        can_access_compositor = hasattr(home_tab.main_window, 'compositor')
        
        print(f"  Access visual_director: {'✅' if can_access_visual else '❌'}")
        print(f"  Access audio_engine: {'✅' if can_access_audio else '❌'}")
        print(f"  Access compositor: {'✅' if can_access_compositor else '❌'}")
    
    # ===== TEST 4: SessionRunnerTab Wiring =====
    print("\n[TEST 4] SessionRunnerTab Engine Wiring")
    print("-" * 70)
    
    session_runner_tab = home_tab.session_runner_tab
    
    # Check if SessionRunnerTab has engines
    has_visual_director = hasattr(session_runner_tab, 'visual_director')
    has_audio_engine = hasattr(session_runner_tab, 'audio_engine')
    has_compositor = hasattr(session_runner_tab, 'compositor')
    
    print(f"  SessionRunnerTab.visual_director: {'✅' if has_visual_director else '❌'}")
    print(f"  SessionRunnerTab.audio_engine: {'✅' if has_audio_engine else '❌'}")
    print(f"  SessionRunnerTab.compositor: {'✅' if has_compositor else '❌'}")
    
    if has_visual_director:
        vd = session_runner_tab.visual_director
        print(f"    - visual_director is None: {vd is None}")
        if vd is not None:
            print(f"    - visual_director type: {type(vd).__name__}")
    
    if has_audio_engine:
        ae = session_runner_tab.audio_engine
        print(f"    - audio_engine is None: {ae is None}")
        if ae is not None:
            print(f"    - audio_engine type: {type(ae).__name__}")
    
    if has_compositor:
        comp = session_runner_tab.compositor
        print(f"    - compositor is None: {comp is None}")
        if comp is not None:
            print(f"    - compositor type: {type(comp).__name__}")
    
    # ===== TEST 5: SessionRunner Creation =====
    print("\n[TEST 5] SessionRunner Instantiation")
    print("-" * 70)
    
    session_runner = getattr(session_runner_tab, 'session_runner', None)
    
    if session_runner:
        print("  ✅ SessionRunner exists")
        
        # Check SessionRunner has engines
        sr_has_visual = hasattr(session_runner, 'visual_director')
        sr_has_audio = hasattr(session_runner, 'audio_engine')
        sr_has_compositor = hasattr(session_runner, 'compositor')
        
        print(f"  SessionRunner.visual_director: {'✅' if sr_has_visual else '❌'}")
        print(f"  SessionRunner.audio_engine: {'✅' if sr_has_audio else '❌'}")
        print(f"  SessionRunner.compositor: {'✅' if sr_has_compositor else '❌'}")
        
        if sr_has_visual:
            print(f"    - Type: {type(session_runner.visual_director).__name__}")
        if sr_has_audio:
            print(f"    - Type: {type(session_runner.audio_engine).__name__}")
        if sr_has_compositor:
            print(f"    - Type: {type(session_runner.compositor).__name__}")
    else:
        print("  ⚠️  SessionRunner not yet created (normal if no session loaded)")
    
    # ===== TEST 6: Compositor Activation Test =====
    print("\n[TEST 6] Compositor Activation API")
    print("-" * 70)
    
    if window.compositor:
        comp = window.compositor
        
        # Check initial state
        initial_active = getattr(comp, '_active', None)
        print(f"  Initial _active state: {initial_active}")
        
        # Test activation
        try:
            comp.set_active(True)
            print("  ✅ compositor.set_active(True) - SUCCESS")
            
            active_after_enable = getattr(comp, '_active', None)
            print(f"    - _active after enable: {active_after_enable}")
        except Exception as e:
            print(f"  ❌ compositor.set_active(True) - FAILED: {e}")
        
        # Test deactivation
        try:
            comp.set_active(False)
            print("  ✅ compositor.set_active(False) - SUCCESS")
            
            active_after_disable = getattr(comp, '_active', None)
            print(f"    - _active after disable: {active_after_disable}")
        except Exception as e:
            print(f"  ❌ compositor.set_active(False) - FAILED: {e}")
    else:
        print("  ❌ No compositor available")
    
    # ===== FINAL SUMMARY =====
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    all_engines_ok = all([
        window.spiral_director is not None,
        window.compositor is not None,
        window.visual_director is not None,
        window.audio_engine is not None,
    ])
    
    tab_wiring_ok = all([
        hasattr(session_runner_tab, 'visual_director'),
        hasattr(session_runner_tab, 'audio_engine'),
        hasattr(session_runner_tab, 'compositor'),
    ])
    
    compositor_api_ok = (
        window.compositor is not None and
        hasattr(window.compositor, 'set_active')
    )
    
    print(f"\n  Engine Initialization: {'✅ PASS' if all_engines_ok else '❌ FAIL'}")
    print(f"  Tab Wiring: {'✅ PASS' if tab_wiring_ok else '❌ FAIL'}")
    print(f"  Compositor API: {'✅ PASS' if compositor_api_ok else '❌ FAIL'}")
    
    overall = all_engines_ok and tab_wiring_ok and compositor_api_ok
    print(f"\n  OVERALL: {'✅ ALL TESTS PASSED' if overall else '❌ SOME TESTS FAILED'}")
    print()
    
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(test_engine_wiring())
