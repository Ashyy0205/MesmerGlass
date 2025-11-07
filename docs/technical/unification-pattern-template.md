# Unification Pattern Template

**Template for Creating Unified Systems in MesmerGlass**  
*Based on successful spiral speed unification*

---

## Overview

This document provides a template for creating unified systems across MesmerGlass applications, based on the successful spiral speed unification. Use this pattern for any functionality that needs to work consistently between VMC, Launcher, and other applications.

---

## Unification Checklist

### Phase 1: Analysis
- [ ] **Identify Inconsistencies** - Document differences between applications
- [ ] **Root Cause Analysis** - Find why applications behave differently  
- [ ] **Define Requirements** - Specify exact behavior needed
- [ ] **Design Single Source of Truth** - Plan centralized calculation/logic

### Phase 2: Implementation
- [ ] **Create Central Module** - Single file with unified logic
- [ ] **Design Clean API** - Simple, consistent function signatures
- [ ] **Update All Applications** - Modify to use central module
- [ ] **Maintain Compatibility** - Keep existing APIs working during transition

### Phase 3: Validation  
- [ ] **Create Test Framework** - Automated validation across applications
- [ ] **Mathematical Verification** - Prove calculations are correct
- [ ] **Cross-Application Testing** - Verify identical behavior
- [ ] **Performance Validation** - Ensure no regression

### Phase 4: Documentation
- [ ] **Technical Documentation** - Implementation details and architecture
- [ ] **Quick Reference** - Developer integration guide
- [ ] **Migration Guide** - How to update existing code
- [ ] **Template Extension** - How to apply pattern to other systems

---

## File Structure Template

```
mesmerglass/[domain]/
├── [feature]_unified.py        # ← Central calculation module
├── [existing_module].py        # ← Updated to use unified module
└── tests/
    └── test_[feature]_unified.py

docs/technical/
├── [feature]-unification.md    # ← Comprehensive documentation
├── [feature]-quick-reference.md # ← Developer guide
└── unification-pattern-template.md  # ← This file

scripts/
├── [feature]_multi_test.py     # ← Cross-application validation
├── visual_mode_creator.py      # ← Updated to use unified API
└── [feature]_speed_test_mode.py # ← Test mode for validation

mesmerglass/ui/
└── launcher.py                 # ← Updated to use unified API
```

---

## Code Template

### 1. Central Unified Module

**File: `mesmerglass/[domain]/[feature]_unified.py`**

```python
"""
Unified [Feature] Calculation Module

This module provides consistent [feature] calculations for all MesmerGlass applications.
Converts [input_units] directly to [output_units].

Key insight: [parameter] should represent actual [units], not a multiplier.
"""

import math
from typing import Optional, Tuple


class [Feature]Calculator:
    """Unified [feature] calculation for consistent behavior across applications"""
    
    @staticmethod
    def [input]_to_[output](input_value: float, context_param: float = 60.0) -> float:
        """
        Convert [input_units] to [output_units].
        
        Args:
            input_value: [Description] (e.g., 4.0 = 4 [input_units])
            context_param: [Context description] (default [default_value])
            
        Returns:
            [Output description] (0.0 to 1.0 = [meaning])
            
        Example:
            4.0 [input_units] = 4/60 = 0.0667 [intermediate]/sec = 0.0667 [output]/sec
            8.0 [input_units] = 8/60 = 0.1333 [intermediate]/sec = 0.1333 [output]/sec
        """
        return input_value / 60.0  # Replace with actual formula
    
    @staticmethod 
    def [input]_to_[output]_per_frame(input_value: float, fps: float = 60.0) -> float:
        """
        Convert [input_units] to [output_units] per frame.
        
        Args:
            input_value: [Description]
            fps: Frames per second (default 60 FPS)
            
        Returns:
            [Output] increment per frame
            
        Example:
            4.0 [input_units] at 60 FPS = (4/60) / 60 = 0.0011 [output]/frame
            8.0 [input_units] at 60 FPS = (8/60) / 60 = 0.0022 [output]/frame
        """
        output_per_second = [Feature]Calculator.[input]_to_[output](input_value)
        return output_per_second / fps
    
    @staticmethod
    def validate_[feature]_calculation(
        target_input: float, 
        measured_output: float,
        tolerance: float = 0.05
    ) -> tuple[bool, float, str]:
        """
        Validate [feature] calculation accuracy.
        
        Args:
            target_input: Target [input_units]
            measured_output: Measured [output_units]
            tolerance: Acceptable error percentage (0.05 = 5%)
            
        Returns:
            (is_accurate, accuracy_percentage, status_message)
        """
        expected_output = [Feature]Calculator.[input]_to_[output](target_input)
        
        if expected_output == 0:
            return False, 0.0, "Zero target - cannot validate"
            
        accuracy = 1.0 - abs(measured_output - expected_output) / expected_output
        is_accurate = accuracy >= (1.0 - tolerance)
        
        status = "ACCURATE" if is_accurate else "INACCURATE"
        return is_accurate, accuracy * 100.0, status


# Convenience functions for backward compatibility
def [feature]_conversion(input_value: float, context: float = 60.0) -> float:
    """Quick conversion: [input_units] → [output_units]"""
    return [Feature]Calculator.[input]_to_[output]_per_frame(input_value, context)

def validate_[feature]_measurement(target: float, measured: float) -> tuple[bool, float]:
    """Quick validation: Check if measured [output] matches target [input]"""
    expected = [Feature]Calculator.[input]_to_[output](target)
    
    is_accurate, accuracy_pct, _ = [Feature]Calculator.validate_[feature]_calculation(
        target, measured
    )
    
    return is_accurate, accuracy_pct
```

### 2. Updated Existing Module

**File: `mesmerglass/[domain]/[existing_module].py`**

```python
def [operation_method](self, legacy_param: float):
    """
    [Operation description] using direct [input_units] calculation instead of legacy formula.
    
    NEW APPROACH: [parameter] is treated as actual [input_units].
    This bypasses the legacy formula and directly converts [input_units] to [output_units].
    
    Args:
        legacy_param: Legacy parameter (ignored in new [input_units] mode)
                     To maintain compatibility with existing calls like [method](4.0)
    """
    # NEW: Direct [input_units] to [output_units] conversion
    from mesmerglass.[domain].[feature]_unified import [feature]_conversion
    
    # Calculate [output] increment for 60 FPS (assuming this is called at 60 Hz)
    output_increment = [feature]_conversion(self.[parameter], fps=60.0)
    
    # Use high-precision accumulator to prevent drift  
    self._[accumulator] += output_increment
    
    # Normalize when crossing boundaries (prevents precision loss)
    if self._[accumulator] >= 1.0:
        full_cycles = int(self._[accumulator])
        self._[counter] += full_cycles
        self._[accumulator] -= full_cycles
    elif self._[accumulator] < 0.0:
        full_cycles = int(-self._[accumulator]) + 1
        self._[counter] -= full_cycles
        self._[accumulator] += full_cycles
        
    # Note: state.[value] is updated by update() method which reads from _[accumulator]
    # This separation ensures a single source of truth for the [value] value
```

### 3. Application Integration

**File: `scripts/visual_mode_creator.py`**

```python
def update_[feature](self):
    """Update [feature] animation using standard [operation] method."""
    # Use standard [feature] [operation] - the method now handles [input_units] calculation internally
    self.director.[operation_method](4.0)  # legacy_param is ignored in new [input_units] mode
    
    # Update other [feature] parameters
    self.director.update(1/60.0)
```

**File: `mesmerglass/ui/launcher.py`**

```python
def _on_[feature]_tick(self):
    # Use standard [feature] [operation] - the method now handles [input_units] calculation internally  
    self.[feature]_director.[operation_method](4.0)  # legacy_param is ignored in new [input_units] mode
    
    # Deterministic dt for tests (60 FPS)
    self.[feature]_director.update(1/60.0)
```

### 4. Test Framework

**File: `scripts/[feature]_multi_test.py`**

```python
#!/usr/bin/env python3
"""
Multi-[Feature] Test - Tests VMC and Launcher at different [feature] settings
===========================================================================

Tests [feature] values: [test_values]
Automatically changes [feature] during test and measures accuracy at each level.
"""

import time
import statistics
from dataclasses import dataclass
from typing import List

@dataclass
class [Feature]TestResult:
    """Results for a single [feature] test"""
    target_[input]: float
    measured_[output]: float
    expected_[output]: float
    accuracy_percentage: float
    sample_count: int
    duration: float
    consistency: float  # std dev

class Multi[Feature]Tester:
    """Tests multiple [feature] settings automatically"""
    
    def __init__(self):
        self.test_[input]s = [4.0, 8.0, 16.0, 24.0]  # Target [feature] values
        self.test_duration_per_[input] = 8.0  # seconds per [feature] test
        
    def test_vmc_multi_[feature](self) -> List[[Feature]TestResult]:
        """Test VMC across multiple [feature] values"""
        # Implementation similar to multi_speed_test.py
        pass
        
    def test_launcher_multi_[feature](self) -> List[[Feature]TestResult]:
        """Test Launcher across multiple [feature] values"""
        # Implementation similar to multi_speed_test.py
        pass
```

---

## Example Applications

### 1. Color Transition Unification

**Problem**: VMC and Launcher use different color interpolation methods
**Solution**: Unified color transition calculator

```python
# mesmerglass/visual/color_unified.py
class ColorTransitionCalculator:
    @staticmethod
    def transition_rate_to_alpha_per_frame(rate_hz: float, fps: float = 60.0) -> float:
        return rate_hz / fps
```

### 2. Audio Synchronization Unification  

**Problem**: Audio timing differs between applications
**Solution**: Unified audio timing calculator

```python
# mesmerglass/audio/timing_unified.py
class AudioTimingCalculator:
    @staticmethod
    def bpm_to_beat_interval(bpm: float) -> float:
        return 60.0 / bpm
```

### 3. Device Command Unification

**Problem**: Buttplug device commands use different timing/intensity patterns
**Solution**: Unified device command calculator

```python
# mesmerglass/devices/command_unified.py
class DeviceCommandCalculator:
    @staticmethod
    def intensity_to_device_value(intensity_percent: float, device_range: tuple) -> int:
        min_val, max_val = device_range
        return int(min_val + (intensity_percent / 100.0) * (max_val - min_val))
```

---

## Validation Patterns

### 1. Mathematical Verification

```python
def test_[feature]_calculation():
    """Verify [feature] calculation is mathematically correct"""
    # Test known values
    assert [feature]_conversion(4.0) == pytest.approx(0.001111, rel=1e-5)
    assert [feature]_conversion(8.0) == pytest.approx(0.002222, rel=1e-5)
```

### 2. Cross-Application Consistency

```python
def test_[feature]_consistency():
    """Verify VMC and Launcher produce identical results"""
    vmc_result = run_vmc_[feature]_test(target=8.0)
    launcher_result = run_launcher_[feature]_test(target=8.0)
    
    assert abs(vmc_result - launcher_result) < 0.01  # 1% tolerance
```

### 3. Regression Testing

```python
def test_[feature]_regression():
    """Verify new system doesn't break existing functionality"""
    # Test that existing calls still work
    legacy_result = legacy_[feature]_method(4.0)
    unified_result = unified_[feature]_method(4.0)
    
    # Results should be equivalent (or better)
    assert unified_result >= legacy_result * 0.95  # Allow 5% improvement
```

---

## Documentation Template

### Comprehensive Documentation

Create `docs/technical/[feature]-unification.md` with sections:
1. **Overview** - Problem statement and solution summary
2. **Architecture** - Component diagram and file structure  
3. **Implementation Details** - Code examples and API reference
4. **Mathematical Foundation** - Formulas and validation
5. **Migration Guide** - Before/after code examples
6. **Testing and Validation** - Test framework and results
7. **Best Practices** - Usage guidelines and troubleshooting

### Quick Reference

Create `docs/technical/[feature]-quick-reference.md` with:
1. **Quick Integration Guide** - 3-step process
2. **API Reference** - Function signatures and examples
3. **Testing Commands** - Command-line validation
4. **Troubleshooting** - Common issues and solutions

---

## Success Criteria

A successful unification should achieve:

- ✅ **Mathematical Accuracy**: Calculations are provably correct
- ✅ **Cross-Application Consistency**: VMC and Launcher behave identically  
- ✅ **Backward Compatibility**: Existing code continues to work
- ✅ **Performance**: No significant performance regression
- ✅ **Maintainability**: Single source of truth, clear code
- ✅ **Testability**: Comprehensive automated validation
- ✅ **Documentation**: Clear integration and troubleshooting guides

---

## Next Steps

To apply this pattern to a new system:

1. **Identify Target System** - Choose inconsistent functionality
2. **Follow Checklist** - Complete all phases systematically  
3. **Use Code Templates** - Adapt templates to specific domain
4. **Create Test Framework** - Build validation before implementation
5. **Document Thoroughly** - Enable other developers to use/extend

This pattern should become the standard approach for any shared functionality in MesmerGlass, ensuring consistency, reliability, and maintainability across all applications.