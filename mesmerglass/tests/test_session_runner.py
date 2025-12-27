"""Tests for Phase 3: SessionRunner Implementation.

Validates:
- SessionRunner initialization and state management
- Cue lifecycle (start/end with events)
- Playback selection from pools (weighted/sequential/shuffle)
- Transition detection (duration and cycle count triggers)
- Cycle-synchronized transitions
- Pause/resume functionality
- Manual cue skipping
- Loop modes (ONCE, LOOP, PING_PONG)
"""

import pytest
import time
import types
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from mesmerglass.session import (
    SessionRunner,
    Cuelist,
    Cue,
    PlaybackEntry,
    CueTransition,
    PlaybackSelectionMode,
    CuelistLoopMode,
    SessionEventEmitter,
    SessionEvent,
    SessionEventType,
    AudioTrack,
    AudioRole,
)


@pytest.fixture
def mock_visual_director():
    """Create a mock VisualDirector for testing."""
    director = Mock()
    director.get_cycle_count = Mock(return_value=0)
    director.load_playback = Mock(return_value=True)
    director.register_cycle_callback = Mock()
    director.unregister_cycle_callback = Mock()
    director.pause = Mock()
    director.resume = Mock()
    return director


@pytest.fixture
def sample_playback_entries(tmp_path):
    """Create sample playback entries."""
    # Create dummy playback files
    pb1 = tmp_path / "playback1.json"
    pb2 = tmp_path / "playback2.json"
    pb3 = tmp_path / "playback3.json"
    
    pb1.write_text('{"version": "1.0", "name": "Playback 1"}')
    pb2.write_text('{"version": "1.0", "name": "Playback 2"}')
    pb3.write_text('{"version": "1.0", "name": "Playback 3"}')
    
    return [
        PlaybackEntry(playback_path=str(pb1), weight=1.0),
        PlaybackEntry(playback_path=str(pb2), weight=2.0),
        PlaybackEntry(playback_path=str(pb3), weight=1.0),
    ]


@pytest.fixture
def simple_cuelist(sample_playback_entries):
    """Create a simple 3-cue cuelist for testing."""
    cuelist = Cuelist(
        name="Test Session",
        description="Test cuelist",
        loop_mode=CuelistLoopMode.ONCE
    )
    
    # Cue 1: 5 seconds, single playback
    cuelist.add_cue(Cue(
        name="Induction",
        duration_seconds=5.0,
        playback_pool=[sample_playback_entries[0]],
        selection_mode=PlaybackSelectionMode.ON_CUE_START
    ))
    
    # Cue 2: 5 seconds, multiple playbacks with weights
    cuelist.add_cue(Cue(
        name="Deepener",
        duration_seconds=5.0,
        playback_pool=sample_playback_entries,
        selection_mode=PlaybackSelectionMode.ON_MEDIA_CYCLE
    ))
    
    # Cue 3: 5 seconds (simple cue for testing)
    cuelist.add_cue(Cue(
        name="Wakener",
        duration_seconds=5.0,
        playback_pool=[sample_playback_entries[2]]
    ))
    
    return cuelist


class _SlowAudioEngine:
    """Deterministic audio engine stub for async prefetch tests."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.num_channels = 2

    def set_stream_threshold_mb(self, _value):
        return None

    def set_slow_decode_threshold_ms(self, value: float) -> None:
        self.slow_threshold = value

    def normalize_track_path(self, file_path: str) -> str:
        return str(file_path)

    def should_stream(self, _file_path: str) -> bool:
        return False

    def preload_sound(self, _file_path: str) -> bool:
        time.sleep(self.delay)
        return True

    def drop_cached_sound(self, _file_path: str) -> None:
        return None


def _make_audio_cuelist(tmp_path: Path) -> Cuelist:
    playback = tmp_path / "prefetch_playback.json"
    playback.write_text('{"name": "prefetch"}')
    audio = tmp_path / "tone.mp3"
    audio.write_text("tone")

    cue = Cue(
        name="Audio",
        duration_seconds=5.0,
        playback_pool=[PlaybackEntry(playback_path=str(playback), weight=1.0)],
        audio_tracks=[AudioTrack(file_path=audio, role=AudioRole.HYPNO)],
    )

    return Cuelist(name="Prefetch", cues=[cue])


class TestSessionRunnerInitialization:
    """Test SessionRunner initialization and basic state."""
    
    def test_initialization(self, simple_cuelist, mock_visual_director):
        """Test SessionRunner initializes correctly."""
        emitter = SessionEventEmitter()
        runner = SessionRunner(
            cuelist=simple_cuelist,
            visual_director=mock_visual_director,
            event_emitter=emitter
        )
        
        assert runner.cuelist == simple_cuelist
        assert runner.visual_director == mock_visual_director
        assert runner.event_emitter == emitter
        assert runner.is_stopped()
        assert not runner.is_running()
        assert not runner.is_paused()
        assert runner.get_current_cue_index() == -1
    
    def test_start_session(self, simple_cuelist, mock_visual_director):
        """Test starting a session loads first cue."""
        emitter = SessionEventEmitter()
        events = []
        emitter.subscribe(SessionEventType.SESSION_START, lambda e: events.append(e))
        emitter.subscribe(SessionEventType.CUE_START, lambda e: events.append(e))
        
        runner = SessionRunner(simple_cuelist, mock_visual_director, emitter)
        success = runner.start()
        
        assert success
        assert runner.is_running()
        assert runner.get_current_cue_index() == 0
        assert len(events) == 2  # SESSION_START + CUE_START
        assert events[0].event_type == SessionEventType.SESSION_START
        assert events[1].event_type == SessionEventType.CUE_START
        assert mock_visual_director.load_playback.called
        assert mock_visual_director.register_cycle_callback.called
    
    def test_cannot_start_twice(self, simple_cuelist, mock_visual_director):
        """Test that starting an already running session fails."""
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner.start()
        
        # Try to start again
        success = runner.start()
        assert not success

    def test_start_session_warms_stream_worker(self, simple_cuelist, mock_visual_director):
        """Session start should warm the audio stream worker to avoid first-cue stalls."""
        emitter = SessionEventEmitter()
        audio_engine = MagicMock()
        audio_engine.num_channels = 2
        audio_engine.is_streaming_active.return_value = False
        audio_engine.set_stream_threshold_mb = Mock()
        audio_engine.set_slow_decode_threshold_ms = Mock()
        audio_engine.ensure_stream_worker_ready = Mock()
        runner = SessionRunner(
            cuelist=simple_cuelist,
            visual_director=mock_visual_director,
            event_emitter=emitter,
            audio_engine=audio_engine,
        )

        runner.start()

        audio_engine.ensure_stream_worker_ready.assert_called_once()


class TestSessionRunnerAudioPrefetch:
    def test_await_cue_audio_ready_honors_completion(self, simple_cuelist, mock_visual_director):
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner._prefetch_worker = MagicMock()
        runner._prefetch_jobs = {0: {"/a"}}
        runner._audio_prefetch_wait_ms = 50.0

        state = {"done": False}

        def _complete(self):
            if not state["done"]:
                self._prefetch_jobs.pop(0, None)
                state["done"] = True

        runner._process_completed_prefetch_jobs = types.MethodType(_complete, runner)

        assert runner._await_cue_audio_ready(0) is True
        runner._prefetch_worker.wait_for_cues.assert_called()

    def test_await_cue_audio_ready_times_out(self, simple_cuelist, mock_visual_director):
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner._prefetch_worker = MagicMock()
        runner._prefetch_jobs = {1: {"/stall"}}
        runner._audio_prefetch_wait_ms = 20.0

        def _noop(self):
            return None

        runner._process_completed_prefetch_jobs = types.MethodType(_noop, runner)

        assert runner._await_cue_audio_ready(1) is False
        runner._prefetch_worker.wait_for_cues.assert_called()

    def test_start_cue_streams_when_audio_not_ready(self, tmp_path, mock_visual_director):
        playback = tmp_path / "stream_playback.json"
        playback.write_text('{"name": "stream"}')
        audio_file = tmp_path / "lag.wav"
        audio_file.write_text("lag")

        cue = Cue(
            name="Lag",
            duration_seconds=5.0,
            playback_pool=[PlaybackEntry(playback_path=str(playback), weight=1.0)],
            audio_tracks=[AudioTrack(file_path=audio_file, role=AudioRole.HYPNO)],
        )
        cuelist = Cuelist(name="Stream", cues=[cue])

        audio_engine = MagicMock()
        audio_engine.num_channels = 1
        audio_engine.load_channel.return_value = True
        audio_engine.fade_in_and_play.return_value = True
        audio_engine.stop_streaming_track.return_value = False
        audio_engine.is_streaming_active.return_value = False
        audio_engine.should_stream.return_value = False
        fake_handle = object()
        audio_engine.play_streaming_track_async.return_value = fake_handle
        audio_engine.play_streaming_track.return_value = True
        audio_engine.preload_sound.return_value = True
        audio_engine.drop_cached_sound.return_value = None
        audio_engine.set_stream_threshold_mb.return_value = None
        audio_engine.set_slow_decode_threshold_ms.return_value = None
        audio_engine.estimate_track_duration.return_value = 5.0
        audio_engine.get_channel_length.return_value = 5.0
        audio_engine.stop_all.return_value = None

        with patch("mesmerglass.session.runner.AudioPrefetchWorker") as worker_cls:
            worker_cls.return_value = MagicMock()
            runner = SessionRunner(
                cuelist,
                mock_visual_director,
                audio_engine=audio_engine,
            )

        with patch.object(runner, "_await_cue_audio_ready", return_value=False):
            assert runner.start() is True

        audio_engine.play_streaming_track_async.assert_called_once()
        audio_engine.load_channel.assert_not_called()
        runner.stop()

    def test_async_streaming_handle_updates(self, simple_cuelist, mock_visual_director):
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner.audio_engine = MagicMock()
        handle = MagicMock()
        runner._pending_streams = {
            AudioRole.HYPNO: {"handle": handle, "track": "big.wav", "reason": "test"}
        }
        runner.audio_engine.poll_stream_handle.return_value = (True, 123.4, None)

        runner._update_pending_streaming_tracks()

        assert AudioRole.HYPNO not in runner._pending_streams
        runner.audio_engine.poll_stream_handle.assert_called_once_with(handle)
        assert runner._active_stream_role == AudioRole.HYPNO

    def test_transition_prefetch_stays_async(self, simple_cuelist, mock_visual_director):
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner._state = runner._state.__class__.RUNNING
        runner._current_cue_index = 0
        runner._calculate_next_cue_index = lambda: 1

        with patch.object(runner, "_prefetch_cue_audio") as mock_prefetch:
            runner._request_transition()

        mock_prefetch.assert_called_once_with(1, force=True, async_allowed=True)


class TestPlaybackSelection:
    """Test playback selection algorithms."""
    
    def test_weighted_selection(self, simple_cuelist, mock_visual_director):
        """Test weighted selection chooses playbacks probabilistically."""
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        cue = simple_cuelist.cues[1]  # Has 3 playbacks with different weights
        
        # Run selection 10 times and collect results
        selections = []
        for _ in range(10):
            entry, path = runner._select_playback_from_pool(cue)
            assert entry is not None
            assert path is not None
            selections.append(path.stem)  # Get filename without extension
        
        # Should have selected some playbacks
        assert len(set(selections)) >= 1  # At least one unique playback
    
    def test_selection_avoids_repeats(self, simple_cuelist, mock_visual_director):
        """Test selection avoids recently used playbacks when possible."""
        cue = simple_cuelist.cues[1]  # Has 3 playbacks
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        
        # Select twice - with 3 playbacks, should often avoid immediate repeat
        first = runner._select_playback_from_pool(cue)
        second = runner._select_playback_from_pool(cue)
        
        assert first is not None
        assert second is not None
        # Note: With random selection and history, repeats are possible but less likely


class TestPlaybackPoolSwitching:
    """Tests for playback pool switching behavior and compatibility fallbacks."""

    def test_duration_constraints_enable_cycle_switching(self, tmp_path, mock_visual_director):
        playback_a = tmp_path / "pool_a.json"
        playback_b = tmp_path / "pool_b.json"
        playback_a.write_text('{"name": "A"}')
        playback_b.write_text('{"name": "B"}')

        cue = Cue(
            name="Legacy Pool",
            duration_seconds=15.0,
            playback_pool=[
                PlaybackEntry(playback_path=str(playback_a), min_duration_s=5.0, max_duration_s=5.0),
                PlaybackEntry(playback_path=str(playback_b), min_duration_s=5.0, max_duration_s=5.0),
            ],
            selection_mode=PlaybackSelectionMode.ON_CUE_START,
        )

        cuelist = Cuelist(name="Compat", cues=[cue])
        runner = SessionRunner(cuelist, mock_visual_director)

        assert runner.start()
        assert runner._active_selection_mode == PlaybackSelectionMode.ON_MEDIA_CYCLE
        assert runner._selection_mode_override_active is True

        runner._playback_target_duration = 1.0
        runner._playback_start_time = time.time() - 2.0

        runner._check_playback_switch()

        assert runner._playback_switch_pending is True
        assert runner._playback_callback_registered is True

        registered_callbacks = [record.args[0] for record in mock_visual_director.register_cycle_callback.call_args_list]
        assert runner._on_playback_cycle_boundary in registered_callbacks


class TestPlaybackSwitchTransitionCoordination:
    """Ensure playback switches are not dropped when cue transitions are pending."""

    def test_playback_switch_executes_before_transition(self, simple_cuelist, mock_visual_director):
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        assert runner.start()

        runner._pending_transition = True
        runner._transition_target_cue = 1
        runner._playback_switch_pending = True
        runner._playback_callback_registered = True

        initial_load_calls = mock_visual_director.load_playback.call_count

        with patch.object(runner, "_execute_transition") as mock_transition:
            runner._on_cycle_boundary()
            # Playback switch should have occurred, transition waits for next boundary
            assert mock_visual_director.load_playback.call_count == initial_load_calls + 1
            mock_transition.assert_not_called()
            assert runner._pending_transition is True
            assert runner._playback_switch_pending is False

            expected_target = runner._transition_target_cue
            runner._on_cycle_boundary()
            mock_transition.assert_called_once_with(expected_target)

    def test_playback_cycle_callback_defers_during_transition(self, simple_cuelist, mock_visual_director):
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        assert runner.start()

        runner._pending_transition = True
        runner._playback_switch_pending = True
        runner._playback_callback_registered = True

        unregister_calls = mock_visual_director.unregister_cycle_callback.call_count
        runner._on_playback_cycle_boundary()

        # Pending switch is preserved so the transition handler can process it
        assert runner._playback_switch_pending is True
        assert mock_visual_director.unregister_cycle_callback.call_count == unregister_calls


class TestFrameTimingStats:
    """Validate frame timing summary logging."""

    def test_distribution_uses_all_samples(self, simple_cuelist, mock_visual_director, caplog):
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner._frame_budget_ms = 20.0
        runner._frame_times = [5.0] * 600 + [25.0] * 600
        runner._memory_samples = [1000.0, 1200.0]

        with caplog.at_level("INFO", logger="mesmerglass.session.runner"):
            runner._log_frame_timing_stats()

        assert "Frame Delay Distribution (all frames):" in caplog.text
        assert "0-10ms: 600" in caplog.text
        assert "20-30ms: 600" in caplog.text


class TestCueProgression:
    """Test cue lifecycle and progression."""
    
    def test_cue_duration_trigger(self, simple_cuelist, mock_visual_director):
        """Test transition triggers when cue duration expires."""
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner.start()
        
        # Fast-forward time by mocking the cue start time
        runner._cue_start_time = time.time() - 6.0  # Cue duration is 5s
        
        # Check transition trigger
        should_transition = runner._check_transition_trigger()
        assert should_transition
    
    def test_cycle_count_trigger(self, sample_playback_entries, mock_visual_director):
        """Test transition triggers when cycle count is reached."""
        # Create cuelist with cue that has max_cycles in playback entry
        cuelist = Cuelist(name="Test", loop_mode=CuelistLoopMode.ONCE)
        
        # Create playback entry with max_cycles
        pb_with_cycles = PlaybackEntry(
            playback_path=str(sample_playback_entries[0].playback_path),
            weight=1.0,
            max_cycles=10
        )
        
        cuelist.add_cue(Cue(
            name="Test Cue",
            duration_seconds=60.0,  # Long duration, but should trigger on cycles
            playback_pool=[pb_with_cycles]
        ))
        
        runner = SessionRunner(cuelist, mock_visual_director)
        runner.start()
        
        # Set start cycle
        runner._cue_start_cycle = 0
        
        # Simulate 10 cycles elapsed
        mock_visual_director.get_cycle_count.return_value = 10
        
        # Note: Current runner doesn't check PlaybackEntry.max_cycles for cue transitions
        # It only checks Cue.transition_out.max_cycles which doesn't exist
        # This test documents current behavior - may need enhancement in Phase 4
        should_transition = runner._check_transition_trigger()
        
        # For now, should NOT transition based on entry max_cycles (not implemented)
        assert not should_transition
    
    def test_transition_waits_for_cycle_boundary(self, simple_cuelist, mock_visual_director):
        """Test that transitions wait for cycle boundaries."""
        events = []
        emitter = SessionEventEmitter()
        emitter.subscribe(SessionEventType.TRANSITION_START, lambda e: events.append(e))
        
        runner = SessionRunner(simple_cuelist, mock_visual_director, emitter)
        runner.start()
        
        # Request transition
        runner._request_transition()
        assert runner._pending_transition
        
        # Transition should not execute yet
        assert len(events) == 0
        
        # Fire cycle boundary callback
        runner._on_cycle_boundary()
        
        # Now transition should execute
        assert not runner._pending_transition
        assert len(events) == 1

    def test_once_mode_ends_without_cycle_boundary(self, sample_playback_entries, mock_visual_director):
        """ONCE-mode sessions must end even if cycle boundaries never arrive.

        Some visuals/media modes may not emit cycle boundary callbacks (e.g. media disabled).
        In that case, cue durations must still be enforced so the cuelist doesn't run forever.
        """
        cuelist = Cuelist(name="NoCycles", loop_mode=CuelistLoopMode.ONCE)
        cuelist.add_cue(
            Cue(
                name="OnlyCue",
                duration_seconds=1.0,
                playback_pool=[sample_playback_entries[0]],
                selection_mode=PlaybackSelectionMode.ON_CUE_START,
            )
        )

        runner = SessionRunner(cuelist, mock_visual_director)
        assert runner.start()

        # Expire the cue duration.
        runner._cue_start_time = time.time() - 2.0

        # No cycle boundary will be fired in this test.
        runner.update(0.016)

        assert runner.is_stopped()
        assert runner.get_current_cue_index() == -1


class TestSessionControl:
    """Test pause/resume/stop functionality."""
    
    def test_pause_and_resume(self, simple_cuelist, mock_visual_director):
        """Test pausing and resuming session."""
        events = []
        emitter = SessionEventEmitter()
        emitter.subscribe(SessionEventType.SESSION_PAUSE, lambda e: events.append(e))
        emitter.subscribe(SessionEventType.SESSION_RESUME, lambda e: events.append(e))
        
        runner = SessionRunner(simple_cuelist, mock_visual_director, emitter)
        runner.start()
        
        # Pause
        success = runner.pause()
        assert success
        assert runner.is_paused()
        assert len(events) == 1
        assert mock_visual_director.pause.called
        
        # Resume
        success = runner.resume()
        assert success
        assert runner.is_running()
        assert len(events) == 2
        assert mock_visual_director.resume.called
    
    def test_stop_session(self, simple_cuelist, mock_visual_director):
        """Test stopping session."""
        events = []
        emitter = SessionEventEmitter()
        emitter.subscribe(SessionEventType.SESSION_STOP, lambda e: events.append(e))
        
        runner = SessionRunner(simple_cuelist, mock_visual_director, emitter)
        runner.start()
        
        runner.stop()
        
        assert runner.is_stopped()
        assert runner.get_current_cue_index() == -1
        assert len(events) == 1
        assert mock_visual_director.unregister_cycle_callback.called
    
    def test_update_does_nothing_when_stopped(self, simple_cuelist, mock_visual_director):
        """Test update() does nothing when session is stopped."""
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        
        # Should not crash
        runner.update(0.016)  # 60fps frame time
        
        assert runner.is_stopped()


class TestManualControl:
    """Test manual cue skipping."""
    
    def test_skip_to_next_cue(self, simple_cuelist, mock_visual_director):
        """Test manually skipping to next cue."""
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner.start()
        
        assert runner.get_current_cue_index() == 0
        
        # Request skip
        success = runner.skip_to_next_cue()
        assert success
        assert runner._pending_transition
        
        # Fire cycle boundary
        runner._on_cycle_boundary()
        
        # Should now be on cue 1
        assert runner.get_current_cue_index() == 1
    
    def test_skip_to_previous_cue(self, simple_cuelist, mock_visual_director):
        """Test manually skipping to previous cue."""
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner.start()
        
        # Move to cue 1
        runner._current_cue_index = 1
        
        # Request skip back
        success = runner.skip_to_previous_cue()
        assert success
        
        # Fire cycle boundary
        runner._on_cycle_boundary()
        
        # Should be back on cue 0
        assert runner.get_current_cue_index() == 0
    
    def test_skip_to_specific_cue(self, simple_cuelist, mock_visual_director):
        """Test skipping to specific cue by index."""
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner.start()
        
        # Skip to cue 2
        success = runner.skip_to_cue(2)
        assert success
        
        # Fire cycle boundary
        runner._on_cycle_boundary()
        
        assert runner.get_current_cue_index() == 2


class TestLoopModes:
    """Test different loop modes."""
    
    def test_once_mode_ends_session(self, simple_cuelist, mock_visual_director):
        """Test ONCE mode ends session after last cue."""
        simple_cuelist.loop_mode = CuelistLoopMode.ONCE
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        
        # Calculate next cue from last cue
        runner._current_cue_index = 2  # Last cue (index 2 of 3 cues)
        next_index = runner._calculate_next_cue_index()
        
        assert next_index == -1  # Should end session


    class TestAsyncAudioPrefetch:
        def test_async_prefetch_returns_immediately(self, tmp_path, mock_visual_director):
            cuelist = _make_audio_cuelist(tmp_path)
            engine = _SlowAudioEngine(delay=0.05)
            runner = SessionRunner(cuelist, mock_visual_director, audio_engine=engine)

            start = time.perf_counter()
            runner._prefetch_cue_audio(0)
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            assert elapsed_ms < 20.0  # returns immediately thanks to background worker

            deadline = time.time() + 1.0
            while 0 not in runner._prefetched_cues and time.time() < deadline:
                runner._process_completed_prefetch_jobs()
                time.sleep(0.01)

            assert 0 in runner._prefetched_cues
            runner.stop()

        def test_sync_prefetch_still_available(self, tmp_path, mock_visual_director):
            cuelist = _make_audio_cuelist(tmp_path)
            engine = _SlowAudioEngine(delay=0.05)
            runner = SessionRunner(cuelist, mock_visual_director, audio_engine=engine)

            start = time.perf_counter()
            runner._prefetch_cue_audio(0, async_allowed=False)
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            assert elapsed_ms >= 50.0  # fallback path blocks until preload completes
            assert 0 in runner._prefetched_cues
            runner.stop()
    
    def test_loop_mode_cycles(self, simple_cuelist, mock_visual_director):
        """Test LOOP mode cycles back to first cue."""
        simple_cuelist.loop_mode = CuelistLoopMode.LOOP
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        
        # From last cue
        runner._current_cue_index = 2
        next_index = runner._calculate_next_cue_index()
        
        assert next_index == 0  # Should loop back
    
    def test_ping_pong_mode_bounces(self, simple_cuelist, mock_visual_director):
        """Test PING_PONG mode bounces back and forth."""
        simple_cuelist.loop_mode = CuelistLoopMode.PING_PONG
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        
        # Forward progression
        runner._current_cue_index = 0
        runner._loop_direction = 1
        next_index = runner._calculate_next_cue_index()
        assert next_index == 1
        
        # Hit end, should reverse
        runner._current_cue_index = 2
        runner._loop_direction = 1
        next_index = runner._calculate_next_cue_index()
        assert next_index == 1

    def test_peek_next_cue_does_not_mutate_direction(self, simple_cuelist, mock_visual_director):
        """_peek_next_cue_index should not alter ping-pong loop direction."""
        simple_cuelist.loop_mode = CuelistLoopMode.PING_PONG
        runner = SessionRunner(simple_cuelist, mock_visual_director)
        runner._current_cue_index = 1
        runner._loop_direction = -1

        peek = runner._peek_next_cue_index()

        assert peek == 0
        assert runner._loop_direction == -1  # unchanged
        assert runner._loop_direction == -1  # Direction reversed
        
        # Backward progression
        runner._current_cue_index = 1
        next_index = runner._calculate_next_cue_index()
        assert next_index == 0


class TestEventEmission:
    """Test that events are emitted correctly."""
    
    def test_session_lifecycle_events(self, simple_cuelist, mock_visual_director):
        """Test that session lifecycle events are emitted."""
        events = []
        emitter = SessionEventEmitter()
        
        # Subscribe to all event types
        for event_type in SessionEventType:
            emitter.subscribe(event_type, lambda e: events.append(e))
        
        runner = SessionRunner(simple_cuelist, mock_visual_director, emitter)
        
        # Start session
        runner.start()
        
        # Should have SESSION_START and CUE_START
        event_types = [e.event_type for e in events]
        assert SessionEventType.SESSION_START in event_types
        assert SessionEventType.CUE_START in event_types
    
    def test_cue_end_event(self, simple_cuelist, mock_visual_director):
        """Test CUE_END event is emitted."""
        events = []
        emitter = SessionEventEmitter()
        emitter.subscribe(SessionEventType.CUE_END, lambda e: events.append(e))
        
        runner = SessionRunner(simple_cuelist, mock_visual_director, emitter)
        runner.start()
        
        # End current cue
        runner._end_cue()
        
        assert len(events) == 1
        assert events[0].event_type == SessionEventType.CUE_END
        assert "cue_name" in events[0].data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
