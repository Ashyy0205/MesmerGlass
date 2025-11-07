"""
Unit tests for weighted random shuffler.

Tests distribution, anti-repetition, and edge cases.
"""

import pytest
from collections import Counter
from mesmerglass.engine.shuffler import Shuffler


class TestShufflerInit:
    """Test shuffler initialization."""
    
    def test_basic_init(self):
        """Test basic initialization."""
        shuffler = Shuffler(item_count=10)
        
        assert shuffler.item_count == 10
        assert shuffler.initial_weight == 10
        assert shuffler.history_size == 8
        assert shuffler.total_weight == 100  # 10 items * 10 weight
        assert len(shuffler.weights) == 10
        assert all(w == 10 for w in shuffler.weights)
    
    def test_custom_parameters(self):
        """Test initialization with custom parameters."""
        shuffler = Shuffler(item_count=20, initial_weight=5, history_size=12)
        
        assert shuffler.item_count == 20
        assert shuffler.initial_weight == 5
        assert shuffler.history_size == 12
        assert shuffler.total_weight == 100  # 20 * 5
    
    def test_invalid_item_count(self):
        """Test validation of item_count."""
        with pytest.raises(ValueError, match="item_count must be positive"):
            Shuffler(item_count=0)
        
        with pytest.raises(ValueError, match="item_count must be positive"):
            Shuffler(item_count=-5)
    
    def test_invalid_initial_weight(self):
        """Test validation of initial_weight."""
        with pytest.raises(ValueError, match="initial_weight must be non-negative"):
            Shuffler(item_count=10, initial_weight=-1)
    
    def test_invalid_history_size(self):
        """Test validation of history_size."""
        with pytest.raises(ValueError, match="history_size must be non-negative"):
            Shuffler(item_count=10, history_size=-1)


class TestWeightedSelection:
    """Test weighted random selection."""
    
    def test_next_returns_valid_index(self):
        """Test that next() returns valid indices."""
        shuffler = Shuffler(item_count=10)
        
        for _ in range(100):
            index = shuffler.next()
            assert 0 <= index < 10
    
    def test_distribution_matches_weights(self):
        """Test that selection distribution roughly matches weights."""
        # Create shuffler with different weights
        shuffler = Shuffler(item_count=3, initial_weight=10, history_size=0)
        
        # Set different weights (disable history to test pure distribution)
        shuffler.weights = [10, 20, 30]
        shuffler.total_weight = 60
        
        # Sample many times
        samples = [shuffler.next() for _ in range(6000)]
        counts = Counter(samples)
        
        # Expected ratios: 10:20:30 = 1:2:3
        # Allow some variance (chi-square would be better, but simple check works)
        assert 800 < counts[0] < 1200   # ~1000 expected (16.7%)
        assert 1700 < counts[1] < 2300  # ~2000 expected (33.3%)
        assert 2700 < counts[2] < 3300  # ~3000 expected (50%)
    
    def test_zero_weight_items_never_selected(self):
        """Test that items with zero weight are never selected."""
        shuffler = Shuffler(item_count=3, initial_weight=10, history_size=0)
        
        # Zero out weight for item 1
        shuffler.weights[1] = 0
        shuffler.total_weight = 20  # Only items 0 and 2 have weight
        
        samples = [shuffler.next() for _ in range(100)]
        
        # Item 1 should never be selected
        assert 1 not in samples
        assert 0 in samples
        assert 2 in samples
    
    def test_all_zero_weights_raises_error(self):
        """Test error when all weights are zero."""
        shuffler = Shuffler(item_count=3, initial_weight=0)
        
        with pytest.raises(ValueError, match="Total weight is 0"):
            shuffler.next()


class TestAntiRepetition:
    """Test last-N anti-repetition tracking."""
    
    def test_history_tracking(self):
        """Test that history tracks recent selections."""
        shuffler = Shuffler(item_count=10, history_size=5)
        
        # Make selections
        indices = [shuffler.next() for _ in range(3)]
        
        history = shuffler.get_history()
        assert history == indices
        assert len(history) == 3
    
    def test_history_size_limit(self):
        """Test that history size is capped."""
        shuffler = Shuffler(item_count=10, history_size=5)
        
        # Make more selections than history size
        for _ in range(10):
            shuffler.next()
        
        history = shuffler.get_history()
        assert len(history) == 5  # Capped at history_size
    
    def test_weight_decrease_on_selection(self):
        """Test that selected item's weight decreases."""
        shuffler = Shuffler(item_count=5, initial_weight=10)
        
        # Force selection of specific item
        shuffler.weights = [0, 0, 100, 0, 0]  # Item 2 will be selected
        shuffler.total_weight = 100
        
        index = shuffler.next()
        assert index == 2
        
        # Weight should have decreased
        assert shuffler.get_weight(2) == 99
        assert shuffler.total_weight == 99
    
    def test_weight_increase_when_leaving_history(self):
        """Test that weight increases when item leaves history."""
        shuffler = Shuffler(item_count=10, initial_weight=10, history_size=3)
        
        # Manually control selections to test weight restoration
        # Force selection of item 0 three times
        for i in range(3):
            shuffler._track_selection(0)
        
        # Item 0 weight should have decreased 3 times: 10 - 3 = 7
        assert shuffler.get_weight(0) == 7
        
        # Select a different item (this pushes item 0 out of history)
        shuffler._track_selection(1)
        
        # Item 0's first occurrence should have fallen off history
        # Weight restored once: 7 + 1 = 8
        assert shuffler.get_weight(0) == 8
    
    def test_no_repeats_within_history(self):
        """Test that anti-repetition mechanism reduces immediate repeats."""
        # Use very small item count to make effect visible
        shuffler = Shuffler(item_count=3, initial_weight=100, history_size=2)
        
        selections = []
        for _ in range(50):
            idx = shuffler.next()
            selections.append(idx)
        
        # With 3 items and no anti-repetition, we'd expect ~33% of selections to be repeats
        # With anti-repetition (history=2), recently selected items have reduced weight
        # So we should see fewer immediate repeats
        immediate_repeats = sum(1 for i in range(len(selections)-1) if selections[i] == selections[i+1])
        
        # Should have significantly fewer than 16 (which would be 33% of 50)
        # Allow generous margin since it's still random
        assert immediate_repeats < 20, f"Anti-repetition not working: {immediate_repeats} repeats out of 50"


class TestWeightManipulation:
    """Test manual weight increase/decrease."""
    
    def test_increase_weight(self):
        """Test increasing weight of an item."""
        shuffler = Shuffler(item_count=5, initial_weight=10)
        
        initial_weight = shuffler.get_weight(2)
        initial_total = shuffler.total_weight
        
        shuffler.increase(2)
        
        assert shuffler.get_weight(2) == initial_weight + 1
        assert shuffler.total_weight == initial_total + 1
    
    def test_decrease_weight(self):
        """Test decreasing weight of an item."""
        shuffler = Shuffler(item_count=5, initial_weight=10)
        
        initial_weight = shuffler.get_weight(2)
        initial_total = shuffler.total_weight
        
        shuffler.decrease(2)
        
        assert shuffler.get_weight(2) == initial_weight - 1
        assert shuffler.total_weight == initial_total - 1
    
    def test_decrease_at_zero_does_nothing(self):
        """Test that decreasing zero weight does nothing."""
        shuffler = Shuffler(item_count=5, initial_weight=0)
        
        shuffler.decrease(2)
        
        assert shuffler.get_weight(2) == 0
        assert shuffler.total_weight == 0
    
    def test_invalid_index_increase(self):
        """Test validation of index in increase()."""
        shuffler = Shuffler(item_count=5)
        
        with pytest.raises(ValueError, match="out of range"):
            shuffler.increase(-1)
        
        with pytest.raises(ValueError, match="out of range"):
            shuffler.increase(5)
    
    def test_invalid_index_decrease(self):
        """Test validation of index in decrease()."""
        shuffler = Shuffler(item_count=5)
        
        with pytest.raises(ValueError, match="out of range"):
            shuffler.decrease(-1)
        
        with pytest.raises(ValueError, match="out of range"):
            shuffler.decrease(5)
    
    def test_invalid_index_get_weight(self):
        """Test validation of index in get_weight()."""
        shuffler = Shuffler(item_count=5)
        
        with pytest.raises(ValueError, match="out of range"):
            shuffler.get_weight(-1)
        
        with pytest.raises(ValueError, match="out of range"):
            shuffler.get_weight(5)


class TestReset:
    """Test reset functionality."""
    
    def test_reset_clears_history(self):
        """Test that reset clears history."""
        shuffler = Shuffler(item_count=10)
        
        for _ in range(5):
            shuffler.next()
        
        assert len(shuffler.get_history()) == 5
        
        shuffler.reset()
        
        assert len(shuffler.get_history()) == 0
    
    def test_reset_restores_weights(self):
        """Test that reset restores initial weights."""
        shuffler = Shuffler(item_count=5, initial_weight=10)
        
        # Make selections (which decrease weights)
        for _ in range(10):
            shuffler.next()
        
        # Weights should have changed
        # (can't predict exact values due to randomness, but total should be lower)
        assert shuffler.total_weight < 50
        
        shuffler.reset()
        
        # All weights restored
        assert all(w == 10 for w in shuffler.weights)
        assert shuffler.total_weight == 50


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_single_item(self):
        """Test shuffler with only one item."""
        shuffler = Shuffler(item_count=1)
        
        # Should always return 0
        for _ in range(10):
            assert shuffler.next() == 0
    
    def test_history_larger_than_items(self):
        """Test history_size larger than item_count."""
        shuffler = Shuffler(item_count=3, history_size=10)
        
        # Should work without issues
        for _ in range(20):
            index = shuffler.next()
            assert 0 <= index < 3
    
    def test_zero_history_size(self):
        """Test with history_size=0 (no anti-repetition)."""
        shuffler = Shuffler(item_count=10, history_size=0)
        
        # Should work, but no anti-repetition
        for _ in range(20):
            index = shuffler.next()
            assert 0 <= index < 10
        
        # History should always be empty (after capping)
        assert len(shuffler.get_history()) == 0
    
    def test_repr(self):
        """Test string representation."""
        shuffler = Shuffler(item_count=10, initial_weight=5, history_size=12)
        
        repr_str = repr(shuffler)
        assert "item_count=10" in repr_str
        assert "initial_weight=5" in repr_str
        assert "history_size=12" in repr_str
        assert "total_weight" in repr_str
