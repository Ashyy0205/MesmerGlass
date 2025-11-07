# Test Suite Cleanup Summary

## Test Run Results

**Date:** November 3, 2025  
**Total Tests:** 372  
**Passed:** 322 (86.6%)  
**Failed:** 49 (13.2%)  
**Skipped:** 1 (0.3%)  

---

## Failure Categories

### 🔴 Critical - Path Issues (2 failures)
**Status:** ✅ FIXED

#### Files Fixed:
1. **`mesmerglass/cli.py`** - Line 1641
   - **Issue:** Looking for `visual_mode_creator.py` at wrong path
   - **Old:** `_P(__file__).resolve().parents[1] / 'visual_mode_creator.py'`
   - **New:** `_P(__file__).resolve().parents[1] / 'scripts' / 'visual_mode_creator.py'`
   
2. **`mesmerglass/tests/test_visual_mode_media_root.py`**
   - **Issue:** Test looking for VMC at root instead of scripts/
   - **Old:** `candidate / 'visual_mode_creator.py'`
   - **New:** `candidate / 'scripts' / 'visual_mode_creator.py'`

**Tests Fixed:**
- ✅ `test_visual_mode_media_root.py::test_media_root_exists`
- ✅ `test_media_measure.py::test_media_measure_vmc_fallback_timer_produces_samples`

---

### 🟡 Medium Priority - Enum Naming (15 failures)
**Status:** ⏸️ NEEDS INVESTIGATION

**Root Cause:** `SplitMode` enum values were renamed but tests weren't updated

#### Failing Tests:
**test_text_renderer.py (10 failures):**
- `test_split_mode_none` - `SplitMode.NONE` doesn't exist
- `test_split_mode_word` - `SplitMode.SPLIT_WORD` doesn't exist
- `test_split_mode_word_gaps` - `SplitMode.SPLIT_WORD_GAPS` doesn't exist
- `test_split_mode_line` - `SplitMode.SPLIT_LINE` doesn't exist
- `test_split_mode_line_gaps` - `SplitMode.SPLIT_LINE_GAPS` doesn't exist
- `test_split_mode_character` - `SplitMode.CHARACTER` doesn't exist
- `test_split_mode_fill_screen` - `SplitMode.FILL_SCREEN` doesn't exist
- `test_render_very_long_text` - Same
- `test_multiple_consecutive_spaces` - Same
- `test_multiple_consecutive_newlines` - Same

**test_text_subtext.py (5 failures):**
- `test_subtext_vs_fillscreen` - `SplitMode.FILL_SCREEN` doesn't exist
- `test_other_modes_no_continuous_render` - `SplitMode.NONE` doesn't exist
- `test_subtext_band_count` - Mock width() issue
- `test_subtext_band_spacing` - Mock width() issue
- `test_scroll_offset_applied_to_x` - Mock width() issue
- `test_continuous_rendering` - Mock width() issue

**Action Required:**
1. Find current `SplitMode` enum values in codebase
2. Update all test references to match
3. Fix Mock compositor.width() to return int instead of Mock object

---

### 🟡 Medium Priority - TextAnimator API Changes (17 failures)
**Status:** ⏸️ NEEDS INVESTIGATION

**Root Cause:** TextAnimator API was refactored but tests weren't updated

#### Missing Attributes/Methods:
- `TextAnimator._time` - Doesn't exist
- `TextAnimator._alpha` - Doesn't exist
- `TextAnimator.get_recommended_spiral_speed()` - Removed
- `TextAnimator.get_state()` - Removed
- `TextAnimator.__init__(config=...)` - Parameter signature changed

#### Failing Tests (test_text_animator.py):
- `test_init_default_values` - `_time` attribute missing
- `test_init_with_custom_config` - Constructor changed
- `test_default_effect_config` - EffectConfig defaults changed
- `test_set_effect_none` - `_time` attribute missing
- `test_set_effect_fade_in` - `_time` attribute missing
- `test_set_effect_fade_out` - `_time` attribute missing
- `test_set_effect_resets_time` - `_time` behavior changed
- `test_fade_in_starts_transparent` - `_alpha` behavior changed
- `test_get_recommended_spiral_speed_*` (5 tests) - Method removed
- `test_get_state` - Method removed
- `test_reset` - `_time` attribute missing
- `test_negative_delta_time` - `_time` attribute missing
- `test_effect_change_during_animation` - `_time` attribute missing

**Action Required:**
1. Review new TextAnimator API
2. Either:
   - Update tests to match new API, OR
   - Mark tests as obsolete and remove if feature changed

---

### 🟠 Low Priority - Spiral Rotation Logic (7 failures)
**Status:** ⏸️ NEEDS INVESTIGATION

**Root Cause:** Spiral rotation formulas returning 0 phase increment for certain types

#### Failing Tests:
**test_spiral_types.py:**
- `test_rotation_formula` - Expected 0.008069, got 0.0
- `test_trance_uniforms_present` - Missing `uWindowOpacity` uniform
- `test_rotation_increments[60-1.0-...]` - Phase increment = 0.0 (expected 0.00403)
- `test_rotation_increments[60-2.0-...]` - Phase increment = 0.0 (expected 0.00807)
- `test_rotation_increments[60-4.0-...]` - Phase increment = 0.0 (expected 0.01614)
- `test_rotation_increments[180-2.0-...]` - Phase increment = 0.0 (expected 0.00466)
- `test_rotation_increments[360-2.0-...]` - Phase increment = 0.0 (expected 0.00329)

**test_spiral_drift.py:**
- `test_extended_rotation_no_drift` - Accumulator desync (0.9999... vs 0.0)

**Analysis:**
- Tests using "trance" spiral type (ID=3) are failing
- Phase increment calculation returning 0.0 instead of expected values
- Possible bug in trance spiral formula or test expectations

**Action Required:**
1. Check spiral rotation formula for trance type
2. Verify if 0.0 increment is intentional (static spiral?)
3. Update tests or fix formula

---

### 🟠 Low Priority - UI Test Framework (2 failures)
**Status:** ⏸️ NEEDS INVESTIGATION

**Root Cause:** Coroutine StopIteration errors in async UI tests

#### Failing Tests (test_ui.py):
- `test_media_controls` - `RuntimeError: coroutine raised StopIteration`
- `test_text_and_effects` - `RuntimeError: coroutine raised StopIteration`

**Error Details:**
```python
E   StopIteration
E   RuntimeError: coroutine raised StopIteration
```

**Analysis:**
- Tests trying to find QGroupBox widgets but hitting StopIteration
- Using `next(generator)` without default value
- Likely UI structure changed or widgets not being created in test environment

**Action Required:**
1. Update selectors to match current UI structure
2. Add default values to `next()` calls
3. Add better error messages for widget not found

---

### 🔵 Other Issues (6 failures)

#### 1. Missing Example File (1 failure)
**Test:** `test_custom_mode_parity.py::test_custom_mode_settings_parity`  
**Issue:** Expects `mesmerglass/modes/sinking.json` reference file  
**Status:** Optional example file, can skip if missing

#### 2. Session Pack Validation (1 failure)
**Test:** `test_session_pack_path_persistence.py`  
**Issue:** `ValueError: text.items[0].msg must be non-empty string`  
**Analysis:** Test fixture creating invalid session pack

#### 3. VR Format Tests (2 failures)
**Tests:** 
- `test_vr_formats.py::test_choose_best_format_prefers_srgb8a8`
- `test_vr_formats.py::test_choose_best_format_when_none_available_returns_default`

**Issue:** Expected format 0x8C43 (GL_SRGB8_ALPHA8), got 0x8058 (GL_RGBA8)  
**Analysis:** VR format selection logic changed or test expectations wrong

---

## Fixes Applied ✅

### 1. Import Path (Already Fixed)
- ✅ `test_cyclers.py` - Updated `from mesmerglass.engine.cyclers` → `from mesmerglass.mesmerloom.cyclers`

### 2. Visual Mode Creator Paths (Just Fixed)
- ✅ `mesmerglass/cli.py` - Updated VMC path to `scripts/visual_mode_creator.py`
- ✅ `test_visual_mode_media_root.py` - Updated test to look in `scripts/` folder

---

## Recommended Actions

### Immediate (Before Next Commit)
1. ✅ Fix VMC path references (DONE)
2. ⏰ Find and update SplitMode enum values in text tests
3. ⏰ Fix Mock compositor width() to return int

### Short Term (This Week)
1. Review TextAnimator API changes and update/remove obsolete tests
2. Investigate spiral rotation formula for trance type
3. Fix UI test widget selectors

### Optional (Low Priority)
1. Create example sinking.json or skip test if missing
2. Fix session pack validation test
3. Review VR format expectations

---

## Test Organization

### Test Categories
**Unit Tests (Fast):** 280+ tests  
- Spiral math, cyclers, text rendering, device control

**Integration Tests:** 40+ tests  
- CLI commands, UI initialization, session packs

**Slow Tests:** 10+ tests  
- Media measurement, Bluetooth scanning

### Test Structure
```
mesmerglass/tests/
├── conftest.py                    # Fixtures
├── fixtures/                      # Test data
├── mesmerloom/                    # MesmerLoom-specific tests
│   ├── test_gl_compile.py
│   ├── test_launcher_compositor_wiring.py
│   └── test_ui_bindings.py
├── test_animator.py               # Animation system
├── test_audio.py                  # Audio engine
├── test_cli*.py                   # CLI commands (15 files)
├── test_spiral*.py                # Spiral system (5 files)
├── test_text*.py                  # Text system (4 files)
├── test_visual*.py                # Visual system (3 files)
└── ... (35+ more test files)
```

---

## Summary

**Current Status:** 86.6% passing (322/372)

**After Path Fixes:** Expected ~88% passing (326/372)

**After Enum Fixes:** Expected ~92% passing (341/372)

**After Full Cleanup:** Target 95%+ passing (350+/372)

The test suite is in good shape overall. Most failures are from:
1. ✅ File reorganization (fixed)
2. ⏰ API refactoring that tests didn't track (fixable)
3. ⏸️ Possible logic bugs that need investigation

**Priority:** Fix enum issues first (15 tests), then investigate TextAnimator API changes (17 tests).
