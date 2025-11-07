"""
Unit tests for cycler system.

Tests frame-accurate timing, composition patterns, and edge cases.
"""

import pytest
from mesmerglass.mesmerloom.cyclers import (
    Cycler,
    ActionCycler,
    RepeatCycler,
    SequenceCycler,
    ParallelCycler
)


class TestActionCycler:
    """Test ActionCycler - execute callback every N frames."""
    
    def test_basic_action(self):
        """Test action executes at period intervals."""
        counter = [0]
        
        def increment():
            counter[0] += 1
        
        cycler = ActionCycler(period=5, action=increment)
        
        # First 5 frames
        for i in range(5):
            cycler.advance()
            # Action should execute at frame 0
            assert counter[0] == 1
        
        # Next 5 frames
        for i in range(5):
            cycler.advance()
            # Action should execute again at frame 5
            assert counter[0] == 2
    
    def test_action_with_offset(self):
        """Test action with initial offset delay."""
        counter = [0]
        
        def increment():
            counter[0] += 1
        
        cycler = ActionCycler(period=5, action=increment, offset=10)
        
        # First 10 frames (offset period) - no action
        for i in range(10):
            cycler.advance()
            assert counter[0] == 0
        
        # Frame 10 - first action
        cycler.advance()
        assert counter[0] == 1
        
        # Frames 11-14 - no action
        for i in range(4):
            cycler.advance()
            assert counter[0] == 1
        
        # Frame 15 - second action
        cycler.advance()
        assert counter[0] == 2
    
    def test_repeat_count_finite(self):
        """Test action with finite repeat count."""
        counter = [0]
        
        def increment():
            counter[0] += 1
        
        cycler = ActionCycler(period=5, action=increment, repeat_count=3)
        
        # Should execute 3 times total
        for i in range(20):
            cycler.advance()
        
        assert counter[0] == 3
        assert cycler.complete()
    
    def test_repeat_count_infinite(self):
        """Test action with infinite repeats (default)."""
        counter = [0]
        
        def increment():
            counter[0] += 1
        
        cycler = ActionCycler(period=5, action=increment)
        
        # Should never complete
        for i in range(100):
            cycler.advance()
            assert not cycler.complete()
        
        assert counter[0] == 20  # 100 frames / 5 period = 20 executions
    
    def test_length_finite(self):
        """Test length calculation with finite repeats."""
        cycler = ActionCycler(period=10, action=lambda: None, offset=5, repeat_count=3)
        # Length = offset + (period * repeat_count) = 5 + 30 = 35
        assert cycler.length() == 35
    
    def test_length_infinite(self):
        """Test length with infinite repeats."""
        cycler = ActionCycler(period=10, action=lambda: None)
        # Should return very large number
        assert cycler.length() > 999999
    
    def test_progress(self):
        """Test progress calculation."""
        cycler = ActionCycler(period=10, action=lambda: None, repeat_count=5)
        
        assert cycler.progress() == 0.0
        
        for _ in range(25):
            cycler.advance()
        
        # 25 frames out of 50 total = 0.5 progress
        assert cycler.progress() == 0.5
    
    def test_reset(self):
        """Test reset functionality."""
        counter = [0]
        cycler = ActionCycler(period=5, action=lambda: counter.__setitem__(0, counter[0] + 1))
        
        for _ in range(10):
            cycler.advance()
        
        assert counter[0] == 2
        assert cycler.index() == 10
        
        cycler.reset()
        assert cycler.index() == 0
        counter[0] = 0
        
        for _ in range(10):
            cycler.advance()
        
        assert counter[0] == 2
    
    def test_invalid_period(self):
        """Test validation of period parameter."""
        with pytest.raises(ValueError, match="Period must be positive"):
            ActionCycler(period=0, action=lambda: None)
        
        with pytest.raises(ValueError, match="Period must be positive"):
            ActionCycler(period=-5, action=lambda: None)
    
    def test_invalid_offset(self):
        """Test validation of offset parameter."""
        with pytest.raises(ValueError, match="Offset must be non-negative"):
            ActionCycler(period=5, action=lambda: None, offset=-1)


class TestRepeatCycler:
    """Test RepeatCycler - repeat child cycler N times."""
    
    def test_basic_repeat(self):
        """Test basic repetition of child cycler."""
        counter = [0]
        
        child = ActionCycler(period=5, action=lambda: counter.__setitem__(0, counter[0] + 1), repeat_count=1)
        repeat = RepeatCycler(count=3, child=child)
        
        # Should execute child 3 times (3 * 5 = 15 frames)
        for _ in range(20):
            repeat.advance()
        
        assert counter[0] == 3
        assert repeat.complete()
    
    def test_length_calculation(self):
        """Test total length calculation."""
        child = ActionCycler(period=10, action=lambda: None, repeat_count=2)
        repeat = RepeatCycler(count=4, child=child)
        
        # Child length = 10 * 2 = 20
        # Repeat length = 20 * 4 = 80
        assert repeat.length() == 80
    
    def test_index_tracking(self):
        """Test frame index tracking."""
        child = ActionCycler(period=10, action=lambda: None, repeat_count=1)  # Executes at frame 0, length=10
        repeat = RepeatCycler(count=3, child=child)
        
        assert repeat.index() == 0
        assert not repeat.complete()
        
        # Advance to completion (30 frames total)
        for _ in range(30):
            repeat.advance()
        
        assert repeat.complete()
        assert repeat.index() == 30  # Total length
    
    def test_reset(self):
        """Test reset functionality."""
        counter = [0]
        child = ActionCycler(period=5, action=lambda: counter.__setitem__(0, counter[0] + 1), repeat_count=1)
        repeat = RepeatCycler(count=3, child=child)
        
        for _ in range(15):
            repeat.advance()
        
        assert repeat.complete()
        assert counter[0] == 3
        
        repeat.reset()
        counter[0] = 0
        
        assert not repeat.complete()
        assert repeat.index() == 0
        
        for _ in range(15):
            repeat.advance()
        
        assert counter[0] == 3
    
    def test_invalid_count(self):
        """Test validation of repeat count."""
        child = ActionCycler(period=5, action=lambda: None)
        
        with pytest.raises(ValueError, match="Repeat count must be positive"):
            RepeatCycler(count=0, child=child)
        
        with pytest.raises(ValueError, match="Repeat count must be positive"):
            RepeatCycler(count=-1, child=child)


class TestSequenceCycler:
    """Test SequenceCycler - execute cyclers one after another."""
    
    def test_basic_sequence(self):
        """Test basic sequential execution."""
        order = []
        
        child1 = ActionCycler(period=5, action=lambda: order.append(1), repeat_count=1)
        child2 = ActionCycler(period=5, action=lambda: order.append(2), repeat_count=1)
        child3 = ActionCycler(period=5, action=lambda: order.append(3), repeat_count=1)
        
        seq = SequenceCycler([child1, child2, child3])
        
        for _ in range(20):
            seq.advance()
        
        assert order == [1, 2, 3]
        assert seq.complete()
    
    def test_length_calculation(self):
        """Test total length is sum of children."""
        child1 = ActionCycler(period=10, action=lambda: None, repeat_count=1)
        child2 = ActionCycler(period=20, action=lambda: None, repeat_count=1)
        child3 = ActionCycler(period=5, action=lambda: None, repeat_count=1)
        
        seq = SequenceCycler([child1, child2, child3])
        
        # Total = 10 + 20 + 5 = 35
        assert seq.length() == 35
    
    def test_index_tracking(self):
        """Test frame index across sequence."""
        child1 = ActionCycler(period=10, action=lambda: None, repeat_count=1)  # 10 frames
        child2 = ActionCycler(period=10, action=lambda: None, repeat_count=1)  # 10 frames
        
        seq = SequenceCycler([child1, child2])
        
        assert seq.index() == 0
        assert not seq.complete()
        
        # Advance to completion (20 frames total)
        for _ in range(20):
            seq.advance()
        
        assert seq.index() == 20
        assert seq.complete()
    
    def test_reset(self):
        """Test reset functionality."""
        order = []
        child1 = ActionCycler(period=5, action=lambda: order.append(1), repeat_count=1)
        child2 = ActionCycler(period=5, action=lambda: order.append(2), repeat_count=1)
        
        seq = SequenceCycler([child1, child2])
        
        for _ in range(15):
            seq.advance()
        
        assert order == [1, 2]
        assert seq.complete()
        
        seq.reset()
        order.clear()
        
        assert not seq.complete()
        assert seq.index() == 0
        
        for _ in range(15):
            seq.advance()
        
        assert order == [1, 2]
    
    def test_empty_sequence(self):
        """Test validation with empty children list."""
        with pytest.raises(ValueError, match="requires at least one child"):
            SequenceCycler([])


class TestParallelCycler:
    """Test ParallelCycler - execute cyclers simultaneously."""
    
    def test_basic_parallel(self):
        """Test parallel execution of multiple cyclers."""
        counters = [0, 0, 0]
        
        child1 = ActionCycler(period=2, action=lambda: counters.__setitem__(0, counters[0] + 1), repeat_count=5)
        child2 = ActionCycler(period=5, action=lambda: counters.__setitem__(1, counters[1] + 1), repeat_count=2)
        child3 = ActionCycler(period=10, action=lambda: counters.__setitem__(2, counters[2] + 1), repeat_count=1)
        
        par = ParallelCycler([child1, child2, child3])
        
        for _ in range(15):
            par.advance()
        
        # child1: 2 * 5 = 10 frames, executes 5 times
        # child2: 5 * 2 = 10 frames, executes 2 times
        # child3: 10 * 1 = 10 frames, executes 1 time
        assert counters[0] == 5
        assert counters[1] == 2
        assert counters[2] == 1
        assert par.complete()
    
    def test_length_calculation(self):
        """Test length is max of all children."""
        child1 = ActionCycler(period=10, action=lambda: None, repeat_count=1)  # 10 frames
        child2 = ActionCycler(period=20, action=lambda: None, repeat_count=1)  # 20 frames
        child3 = ActionCycler(period=5, action=lambda: None, repeat_count=1)   # 5 frames
        
        par = ParallelCycler([child1, child2, child3])
        
        # Max = 20
        assert par.length() == 20
    
    def test_index_tracking(self):
        """Test index is max across all children."""
        child1 = ActionCycler(period=5, action=lambda: None, repeat_count=2)   # 10 frames
        child2 = ActionCycler(period=10, action=lambda: None, repeat_count=1)  # 10 frames
        
        par = ParallelCycler([child1, child2])
        
        for _ in range(5):
            par.advance()
        
        # Both at frame 5
        assert par.index() == 5
        
        for _ in range(5):
            par.advance()
        
        # Both at frame 10
        assert par.index() == 10
    
    def test_completes_when_all_complete(self):
        """Test completion only when all children complete."""
        child1 = ActionCycler(period=5, action=lambda: None, repeat_count=2)   # 10 frames
        child2 = ActionCycler(period=10, action=lambda: None, repeat_count=2)  # 20 frames
        
        par = ParallelCycler([child1, child2])
        
        for _ in range(10):
            par.advance()
        
        # child1 complete (10 frames), but child2 still running (needs 20 total)
        assert child1.complete()
        assert not child2.complete()
        assert not par.complete()
        
        for _ in range(10):
            par.advance()
        
        # Both complete
        assert par.complete()
    
    def test_reset(self):
        """Test reset functionality."""
        counters = [0, 0]
        child1 = ActionCycler(period=5, action=lambda: counters.__setitem__(0, counters[0] + 1), repeat_count=2)
        child2 = ActionCycler(period=10, action=lambda: counters.__setitem__(1, counters[1] + 1), repeat_count=1)
        
        par = ParallelCycler([child1, child2])
        
        for _ in range(15):
            par.advance()
        
        assert counters[0] == 2
        assert counters[1] == 1
        
        par.reset()
        counters[0] = 0
        counters[1] = 0
        
        for _ in range(15):
            par.advance()
        
        assert counters[0] == 2
        assert counters[1] == 1
    
    def test_empty_parallel(self):
        """Test validation with empty children list."""
        with pytest.raises(ValueError, match="requires at least one child"):
            ParallelCycler([])


class TestNestedCyclers:
    """Test complex nested cycler compositions."""
    
    def test_repeat_of_sequence(self):
        """Test RepeatCycler(SequenceCycler(...))."""
        order = []
        
        seq = SequenceCycler([
            ActionCycler(period=5, action=lambda: order.append('A'), repeat_count=1),
            ActionCycler(period=5, action=lambda: order.append('B'), repeat_count=1)
        ])
        
        repeat = RepeatCycler(count=3, child=seq)
        
        for _ in range(40):
            repeat.advance()
        
        # Should see A, B, A, B, A, B
        assert order == ['A', 'B', 'A', 'B', 'A', 'B']
        assert repeat.complete()
    
    def test_parallel_of_sequences(self):
        """Test ParallelCycler([SequenceCycler(...), ...])."""
        order1 = []
        order2 = []
        
        seq1 = SequenceCycler([
            ActionCycler(period=5, action=lambda: order1.append(1), repeat_count=1),
            ActionCycler(period=5, action=lambda: order1.append(2), repeat_count=1)
        ])
        
        seq2 = SequenceCycler([
            ActionCycler(period=10, action=lambda: order2.append('A'), repeat_count=1),
            ActionCycler(period=10, action=lambda: order2.append('B'), repeat_count=1)
        ])
        
        par = ParallelCycler([seq1, seq2])
        
        for _ in range(25):
            par.advance()
        
        # seq1: 1 at frame 0, 2 at frame 5 (total 10 frames)
        # seq2: A at frame 0, B at frame 10 (total 20 frames)
        assert order1 == [1, 2]
        assert order2 == ['A', 'B']
        assert par.complete()
    
    def test_complex_composition(self):
        """Test deeply nested composition: Repeat(Parallel([Sequence(...), Action(...)]))."""
        counters = {'seq': 0, 'action': 0}
        
        # Sequence that runs for 10 frames
        seq = SequenceCycler([
            ActionCycler(period=5, action=lambda: counters.__setitem__('seq', counters['seq'] + 1), repeat_count=1),
            ActionCycler(period=5, action=lambda: counters.__setitem__('seq', counters['seq'] + 1), repeat_count=1)
        ])
        
        # Action that runs every 2 frames for 10 frames
        action = ActionCycler(period=2, action=lambda: counters.__setitem__('action', counters['action'] + 1), repeat_count=5)
        
        # Run them in parallel (total 10 frames)
        par = ParallelCycler([seq, action])
        
        # Repeat the parallel execution 3 times (total 30 frames)
        repeat = RepeatCycler(count=3, child=par)
        
        for _ in range(35):
            repeat.advance()
        
        # Sequence executes 2 times per iteration * 3 iterations = 6
        assert counters['seq'] == 6
        
        # Action executes 5 times per iteration * 3 iterations = 15
        assert counters['action'] == 15
        
        assert repeat.complete()
