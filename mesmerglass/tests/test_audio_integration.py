"""
Tests for AudioEngine integration with SessionRunner.

Tests cover:
- AudioEngine basic functionality (load, play, fade, stop)
- Audio track loading and playback in cues
- Fade-in timing on cue start
- Fade-out timing on cue end
- Per-channel volume and loop control
- Audio cleanup on session stop
"""

import pytest
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from mesmerglass.engine.audio import AudioEngine
from mesmerglass.session.cue import Cue, PlaybackEntry, AudioTrack, AudioRole
from mesmerglass.session.cuelist import Cuelist
from mesmerglass.session.cuelist import CuelistTransitionMode
from mesmerglass.session.runner import SessionRunner
from mesmerglass.session.audio_prefetch import (
    gather_audio_paths_for_cuelist,
    prefetch_audio_for_cuelist,
)
from mesmerglass.session.audio_prefetch_worker import AudioPrefetchWorker, PrefetchJob


class TestAudioPrefetchUtilities:
    """Unit tests for cuelist-level audio prefetch helpers."""

    def _make_two_cue_list(self, tmp_path: Path) -> Cuelist:
        playback = tmp_path / "pb.json"
        playback.write_text('{"name": "PB"}')
        audio_a = tmp_path / "a.mp3"
        audio_a.write_text("a")
        audio_b = tmp_path / "b.mp3"
        audio_b.write_text("b")

        cue1 = Cue(
            name="Cue A",
            duration_seconds=5.0,
            playback_pool=[PlaybackEntry(playback_path=playback, weight=1.0)],
            audio_tracks=[AudioTrack(file_path=audio_a, role=AudioRole.HYPNO)],
        )
        cue2 = Cue(
            name="Cue B",
            duration_seconds=5.0,
            playback_pool=[PlaybackEntry(playback_path=playback, weight=1.0)],
            audio_tracks=[
                AudioTrack(file_path=audio_a, role=AudioRole.BACKGROUND),
                AudioTrack(file_path=audio_b, role=AudioRole.GENERIC),
            ],
        )
        return Cuelist(name="Utility Test", cues=[cue1, cue2])

    def test_gather_audio_paths_dedupes_in_order(self, tmp_path):
        cuelist = self._make_two_cue_list(tmp_path)
        paths = gather_audio_paths_for_cuelist(cuelist)
        assert len(paths) == 2
        assert paths[0].endswith("a.mp3")
        assert paths[1].endswith("b.mp3")

    def test_gather_audio_paths_respects_max_cues(self, tmp_path):
        cuelist = self._make_two_cue_list(tmp_path)
        paths = gather_audio_paths_for_cuelist(cuelist, max_cues=1)
        assert len(paths) == 1
        assert paths[0].endswith("a.mp3")

    def test_prefetch_audio_for_cuelist_invokes_engine(self, tmp_path):
        cuelist = self._make_two_cue_list(tmp_path)
        engine = MagicMock(spec=AudioEngine)
        engine.prefetch_tracks.return_value = {"a": True, "b": False}

        result = prefetch_audio_for_cuelist(engine, cuelist, max_cues=1)

        engine.prefetch_tracks.assert_called_once()
        # Only first cue requested because max_cues=1
        called_args = engine.prefetch_tracks.call_args[0][0]
        assert len(called_args) == 1
        assert result == {"a": True, "b": False}

    def test_prefetch_audio_reports_progress(self, tmp_path):
        cuelist = self._make_two_cue_list(tmp_path)
        engine = MagicMock(spec=AudioEngine)
        engine.prefetch_tracks.return_value = {}
        engine.preload_sound.side_effect = [True, False]

        progress_events = []

        def _callback(done, total, path, ok):
            progress_events.append((done, total, Path(path).name, ok))

        result = prefetch_audio_for_cuelist(
            engine,
            cuelist,
            progress_callback=_callback,
        )

        assert engine.preload_sound.call_count == 2
        assert result
        assert progress_events == [
            (1, 2, "a.mp3", True),
            (2, 2, "b.mp3", False),
        ]

    def test_audio_prefetch_worker_reports_results(self):
        engine = MagicMock(spec=AudioEngine)
        engine.preload_sound.return_value = True

        worker = AudioPrefetchWorker(engine, max_workers=1)
        job = PrefetchJob(cue_index=0, role=AudioRole.HYPNO, path="/tmp/a.mp3")

        assert worker.submit(job)

        results = []
        deadline = time.time() + 1.0
        while time.time() < deadline:
            results = worker.drain_completed()
            if results:
                break
            time.sleep(0.01)

        worker.shutdown(wait=True)

        assert results
        completed_job, success, exc = results[0]
        assert completed_job == job
        assert success is True
        assert exc is None

    def test_audio_prefetch_worker_wait_for_cue_completion(self):
        engine = MagicMock(spec=AudioEngine)
        gate = threading.Event()

        def _slow_preload(_path):
            gate.wait(timeout=0.05)
            return True

        engine.preload_sound.side_effect = _slow_preload

        worker = AudioPrefetchWorker(engine, max_workers=1)
        job = PrefetchJob(cue_index=2, role=AudioRole.BACKGROUND, path="/tmp/b.mp3")
        assert worker.submit(job)

        assert worker.pending_for_cue(2) == 1

        timer = threading.Timer(0.02, gate.set)
        timer.start()
        worker.wait_for_cues({2}, timeout=0.5)
        timer.cancel()

        worker.shutdown(wait=True)

        assert worker.pending_for_cue(2) == 0
        completed = worker.drain_completed()
        assert completed and completed[0][0] == job


class TestAudioEngineBasics:
    """Test AudioEngine core functionality."""
    
    def test_audio_engine_initialization(self):
        """AudioEngine initializes with specified number of channels."""
        engine = AudioEngine(num_channels=3)
        
        assert engine.num_channels == 3
        assert len(engine._sounds) == 3
        assert len(engine._channels) == 3
        assert len(engine._volumes) == 3
        assert len(engine._lengths) == 3
        assert all(v == 1.0 for v in engine._volumes)
        assert all(length == 0.0 for length in engine._lengths)
    
    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_load_channel(self, mock_mixer):
        """load_channel loads audio file into specified channel."""
        engine = AudioEngine(num_channels=2)
        engine.init_ok = True
        
        mock_sound = MagicMock()
        mock_sound.get_length.return_value = 12.5
        mock_mixer.Sound.return_value = mock_sound
        
        result = engine.load_channel(0, "test.mp3")
        
        assert result is True
        assert engine._sounds[0] == mock_sound
        assert engine._paths[0] == "test.mp3"
        assert engine._lengths[0] == 12.5
        mock_mixer.Sound.assert_called_once()
        called_path = mock_mixer.Sound.call_args[0][0]
        assert str(called_path).endswith("test.mp3")
    
    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_fade_in_and_play(self, mock_mixer):
        """fade_in_and_play starts playback with fade effect."""
        engine = AudioEngine(num_channels=2)
        engine.init_ok = True
        
        mock_sound = MagicMock()
        mock_channel = MagicMock()
        mock_sound.play.return_value = mock_channel
        engine._sounds[0] = mock_sound
        
        result = engine.fade_in_and_play(
            channel=0,
            fade_ms=1000,
            volume=0.7,
            loop=True
        )
        
        assert result is True
        mock_sound.play.assert_called_once_with(loops=-1, fade_ms=1000)
        mock_channel.set_volume.assert_called_once_with(0.7)
        assert engine._volumes[0] == 0.7
        assert engine._looping[0] is True
        assert engine._fading_in[0] is True
    
    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_fade_out_and_stop(self, mock_mixer):
        """fade_out_and_stop fades out and stops playback."""
        engine = AudioEngine(num_channels=2)
        engine.init_ok = True
        
        mock_channel = MagicMock()
        mock_channel.get_busy.return_value = True
        engine._channels[0] = mock_channel
        
        result = engine.fade_out_and_stop(0, fade_ms=500)
        
        assert result is True
        mock_channel.fadeout.assert_called_once_with(500)
        assert engine._fading_out[0] is True
        assert engine._fading_in[0] is False
    
    def test_stop_channel(self):
        """stop_channel immediately stops playback."""
        engine = AudioEngine(num_channels=2)
        engine.init_ok = True
        
        mock_channel = MagicMock()
        engine._channels[0] = mock_channel
        engine._fading_in[0] = True
        engine._fading_out[0] = True
        
        result = engine.stop_channel(0)
        
        assert result is True
        mock_channel.stop.assert_called_once()
        assert engine._channels[0] is None
        assert engine._fading_in[0] is False
        assert engine._fading_out[0] is False
    
    def test_stop_all(self):
        """stop_all stops all channels."""
        engine = AudioEngine(num_channels=3)
        engine.init_ok = True
        
        for i in range(3):
            mock_channel = MagicMock()
            engine._channels[i] = mock_channel
        
        engine.stop_all()
        
        for i in range(3):
            assert engine._channels[i] is None
    
    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_set_volume(self, mock_mixer):
        """set_volume changes channel volume."""
        engine = AudioEngine(num_channels=2)
        engine.init_ok = True
        
        mock_channel = MagicMock()
        mock_channel.get_busy.return_value = True
        engine._channels[0] = mock_channel
        
        result = engine.set_volume(0, 0.5)
        
        assert result is True
        mock_channel.set_volume.assert_called_once_with(0.5)
        assert engine._volumes[0] == 0.5
    
    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_is_playing(self, mock_mixer):
        """is_playing returns correct playback state."""
        engine = AudioEngine(num_channels=2)
        engine.init_ok = True
        
        # Channel 0: playing
        mock_channel_playing = MagicMock()
        mock_channel_playing.get_busy.return_value = True
        engine._channels[0] = mock_channel_playing
        
        # Channel 1: not playing
        engine._channels[1] = None
        
        assert engine.is_playing(0) is True
        assert engine.is_playing(1) is False

    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_preload_sound_uses_cache(self, mock_mixer):
        """preload_sound decodes once and reuses cached buffer."""
        engine = AudioEngine(num_channels=2)
        engine.init_ok = True

        mock_sound = MagicMock()
        mock_sound.get_length.return_value = 5.0
        mock_mixer.Sound.return_value = mock_sound

        assert engine.preload_sound("foo.wav") is True
        assert engine.preload_sound("foo.wav") is True
        assert mock_mixer.Sound.call_count == 1

    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_load_channel_reuses_prefetched_sound(self, mock_mixer):
        """load_channel should not hit disk when sound already cached."""
        engine = AudioEngine(num_channels=1)
        engine.init_ok = True

        mock_sound = MagicMock()
        mock_sound.get_length.return_value = 6.0
        mock_mixer.Sound.return_value = mock_sound

        assert engine.preload_sound("foo.wav") is True
        mock_mixer.Sound.reset_mock()

        result = engine.load_channel(0, "foo.wav")
        assert result is True
        mock_mixer.Sound.assert_not_called()

    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_load_channel_marks_forced_stream_on_memory_error(self, mock_mixer):
        """OOM while decoding pushes the path into forced-stream mode."""
        engine = AudioEngine(num_channels=1)
        engine.init_ok = True

        mock_mixer.Sound.side_effect = Exception("Out of memory")

        assert engine.load_channel(0, "too_big.wav") is False
        assert engine.should_stream("too_big.wav") is True

    def test_prefetch_honors_forced_stream_paths(self, tmp_path):
        """Prefetch marks forced-stream assets as ready without decoding."""
        audio_file = tmp_path / "forced.wav"
        audio_file.write_text("x")

        engine = AudioEngine(num_channels=1)
        engine.init_ok = True
        engine.force_stream_for_path(str(audio_file))

        result = engine.prefetch_tracks([str(audio_file)])
        normalized = str(audio_file.resolve())
        assert result[normalized] is True

    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_slow_decode_forces_streaming(self, mock_mixer, tmp_path):
        """Decodes exceeding threshold automatically switch the asset to streaming."""
        engine = AudioEngine(num_channels=1)
        engine.init_ok = True
        engine.set_slow_decode_threshold_ms(5.0)

        mock_sound = MagicMock()
        mock_sound.get_length.return_value = 4.0
        mock_mixer.Sound.return_value = mock_sound

        path = tmp_path / "slow.wav"
        path.write_text("slow")

        with patch('mesmerglass.engine.audio.time.perf_counter', side_effect=[0.0, 0.01, 0.01]):
            assert engine.preload_sound(str(path)) is True

        assert engine.should_stream(str(path)) is True


class TestSessionRunnerAudioIntegration:
    """Test AudioEngine integration with SessionRunner."""
    
    @pytest.fixture
    def mock_visual_director(self):
        """Mock VisualDirector."""
        director = MagicMock()
        director.load_playback.return_value = True
        director.get_cycle_count.return_value = 0
        return director
    
    @pytest.fixture
    def mock_audio_engine(self):
        """Mock AudioEngine."""
        engine = MagicMock(spec=AudioEngine)
        engine.num_channels = 2
        engine.load_channel.return_value = True
        engine.fade_in_and_play.return_value = True
        engine.fade_out_and_stop.return_value = True
        engine.is_playing.return_value = True
        engine.get_channel_length.return_value = 30.0
        engine.prefetch_tracks.return_value = {}
        engine.should_stream.return_value = False
        engine.play_streaming_track.return_value = False
        engine.stop_streaming_track.return_value = False
        engine.is_streaming_active.return_value = False
        engine.set_stream_threshold_mb.return_value = None
        engine.preload_sound.return_value = True
        engine.estimate_track_duration.return_value = 8.0
        engine.drop_cached_sound.return_value = None
        return engine
    
    @pytest.fixture
    def sample_cuelist_with_audio(self, tmp_path):
        """Create cuelist with audio tracks."""
        # Create dummy playback files
        playback_dir = tmp_path / "playbacks"
        playback_dir.mkdir()
        
        playback1 = playback_dir / "test1.json"
        playback1.write_text('{"name": "Test 1"}')
        
        # Create dummy audio file (won't actually play in tests)
        audio_file = tmp_path / "test_audio.mp3"
        audio_file.write_text("dummy audio")
        
        # Create cue with audio track
        cue = Cue(
            name="Test Cue",
            duration_seconds=10.0,
            playback_pool=[
                PlaybackEntry(playback_path=playback1, weight=1.0)
            ],
            audio_tracks=[
                AudioTrack(
                    file_path=audio_file,
                    volume=0.8,
                    loop=True,
                    fade_in_ms=1000,
                    fade_out_ms=500,
                    role=AudioRole.HYPNO
                )
            ]
        )
        
        cuelist = Cuelist(
            name="Test Cuelist with Audio",
            cues=[cue]
        )
        
        return cuelist

    @pytest.fixture
    def sample_cuelist_two_cues(self, tmp_path):
        """Create cuelist with two cues (each with audio)."""
        playback_dir = tmp_path / "playbacks"
        playback_dir.mkdir()

        playback1 = playback_dir / "test1.json"
        playback1.write_text('{"name": "Test 1"}')
        playback2 = playback_dir / "test2.json"
        playback2.write_text('{"name": "Test 2"}')

        audio1 = tmp_path / "audio1.mp3"
        audio1.write_text("dummy audio 1")
        audio2 = tmp_path / "audio2.mp3"
        audio2.write_text("dummy audio 2")

        cue1 = Cue(
            name="Cue 1",
            duration_seconds=5.0,
            playback_pool=[PlaybackEntry(playback_path=playback1, weight=1.0)],
            audio_tracks=[AudioTrack(file_path=audio1, role=AudioRole.HYPNO)]
        )

        cue2 = Cue(
            name="Cue 2",
            duration_seconds=5.0,
            playback_pool=[PlaybackEntry(playback_path=playback2, weight=1.0)],
            audio_tracks=[AudioTrack(file_path=audio2, role=AudioRole.BACKGROUND)]
        )

        return Cuelist(name="Two Cue Test", cues=[cue1, cue2])
    
    def test_audio_loaded_on_cue_start(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio
    ):
        """Audio tracks are loaded when cue starts."""
        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine
        )
        
        runner.start()
        
        # Verify audio was loaded
        cue = sample_cuelist_with_audio.cues[0]
        track = cue.audio_tracks[0]
        
        mock_audio_engine.load_channel.assert_called_once_with(0, str(track.file_path))
    
    def test_audio_plays_with_fade_in(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio
    ):
        """Audio plays with fade-in when cue starts."""
        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine
        )
        
        runner.start()
        
        # Verify fade-in was called with correct parameters
        cue = sample_cuelist_with_audio.cues[0]
        track = cue.audio_tracks[0]
        mock_audio_engine.fade_in_and_play.assert_called_once_with(
            channel=0,
            fade_ms=track.fade_in_ms,
            volume=track.volume,
            loop=track.loop
        )
    
    def test_audio_fades_out_on_cue_end(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio
    ):
        """Audio fades out when cue ends."""
        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine
        )
        
        runner.start()
        runner.stop()
        
        # Verify fade-out was called
        cue = sample_cuelist_with_audio.cues[0]
        fade_ms = cue.transition_out.duration_ms
        
        # stop_all is called, which internally calls fade_out_and_stop
        mock_audio_engine.stop_all.assert_called_once()
    
    def test_audio_respects_volume_setting(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio
    ):
        """Audio volume is set correctly from AudioTrack."""
        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine
        )
        
        runner.start()
        
        # Check that fade_in_and_play was called with correct volume
        calls = mock_audio_engine.fade_in_and_play.call_args_list
        assert len(calls) == 1
        assert calls[0].kwargs['volume'] == 0.8
    
    def test_audio_respects_loop_setting(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio
    ):
        """Audio loop setting is passed correctly."""
        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine
        )
        
        runner.start()
        
        # Check that fade_in_and_play was called with loop=True
        calls = mock_audio_engine.fade_in_and_play.call_args_list
        assert len(calls) == 1
        assert calls[0].kwargs['loop'] is True

    def test_prefetches_only_active_cue_on_start(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_two_cues,
    ):
        """SessionRunner should only warm cue 0 immediately to avoid extra decoding."""
        runner = SessionRunner(
            cuelist=sample_cuelist_two_cues,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine,
        )

        runner.start()

        seen_paths = [Path(call.args[0]) for call in mock_audio_engine.preload_sound.call_args_list]
        assert any(path.name == "audio1.mp3" for path in seen_paths)
        assert not any(path.name == "audio2.mp3" for path in seen_paths)

    def test_prefetch_window_triggers_before_transition(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_two_cues,
    ):
        """Lead-time window should attempt to prefetch when cue is nearly done."""
        runner = SessionRunner(
            cuelist=sample_cuelist_two_cues,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine,
        )
        runner.start()

        # Simulate we still need cue 1 cached (clear previous mark)
        runner._prefetched_cues.discard(1)
        runner._current_cue_index = 0
        runner._cue_start_time = time.time() - (sample_cuelist_two_cues.cues[0].duration_seconds - 1)
        runner._audio_prefetch_lead_seconds = 2.0

        mock_audio_engine.preload_sound.reset_mock()
        runner._ensure_audio_prefetch_window()

        assert mock_audio_engine.preload_sound.called
    
    def test_audio_engine_update_called(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio
    ):
        """AudioEngine.update() is called during session update."""
        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine
        )
        
        runner.start()
        
        # Reset mock to clear start() calls
        mock_audio_engine.update.reset_mock()
        
        # Call update several times
        for _ in range(5):
            runner.update()
        
        # Verify update was called
        assert mock_audio_engine.update.call_count == 5
    
    def test_multiple_audio_tracks_loaded(
        self,
        mock_visual_director,
        mock_audio_engine,
        tmp_path
    ):
        """Multiple audio tracks are loaded correctly."""
        # Create playback
        playback_dir = tmp_path / "playbacks"
        playback_dir.mkdir()
        playback1 = playback_dir / "test1.json"
        playback1.write_text('{"name": "Test 1"}')
        
        # Create two audio files
        audio1 = tmp_path / "audio1.mp3"
        audio1.write_text("dummy")
        audio2 = tmp_path / "audio2.mp3"
        audio2.write_text("dummy")
        
        # Create cue with two audio tracks
        cue = Cue(
            name="Multi-track Cue",
            duration_seconds=10.0,
            playback_pool=[
                PlaybackEntry(playback_path=playback1, weight=1.0)
            ],
            audio_tracks=[
                AudioTrack(file_path=audio1, volume=0.8, loop=True, role=AudioRole.HYPNO),
                AudioTrack(file_path=audio2, volume=0.5, loop=False, role=AudioRole.BACKGROUND)
            ]
        )
        
        cuelist = Cuelist(name="Multi-track Test", cues=[cue])
        
        runner = SessionRunner(cuelist=cuelist, visual_director=mock_visual_director, audio_engine=mock_audio_engine)
        runner.start()
        
        # Verify both tracks were loaded
        assert mock_audio_engine.load_channel.call_count == 2
        mock_audio_engine.load_channel.assert_any_call(0, str(audio1))
        mock_audio_engine.load_channel.assert_any_call(1, str(audio2))
        
        # Verify both tracks started playing
        assert mock_audio_engine.fade_in_and_play.call_count == 2

    def test_prefetch_runs_before_first_cue(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_two_cues
    ):
        """Audio prefetch executes ahead of first cue load."""
        runner = SessionRunner(
            cuelist=sample_cuelist_two_cues,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine
        )

        runner.start()

        assert any("audio1.mp3" in call.args[0] for call in mock_audio_engine.preload_sound.call_args_list)

    def test_prefetch_runs_for_transition_target(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_two_cues
    ):
        """_request_transition should prefetch next cue audio."""
        runner = SessionRunner(
            cuelist=sample_cuelist_two_cues,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine
        )

        runner.start()
        mock_audio_engine.preload_sound.reset_mock()

        runner._request_transition()

        assert any("audio2.mp3" in call.args[0] for call in mock_audio_engine.preload_sound.call_args_list)

    def test_background_forces_loop(
        self,
        mock_visual_director,
        mock_audio_engine,
        tmp_path
    ):
        """Background track loops even if configuration disables it."""
        playback = tmp_path / "pb.json"
        playback.write_text('{"name":"PB"}')
        hypno = tmp_path / "hypno.mp3"
        hypno.write_text("dummy")
        background = tmp_path / "bg.mp3"
        background.write_text("dummy")

        cue = Cue(
            name="Dual Audio",
            duration_seconds=20,
            playback_pool=[PlaybackEntry(playback_path=playback, weight=1.0)],
            audio_tracks=[
                AudioTrack(file_path=hypno, volume=0.9, loop=False, role=AudioRole.HYPNO),
                AudioTrack(file_path=background, volume=0.3, loop=False, role=AudioRole.BACKGROUND)
            ]
        )

        cuelist = Cuelist(name="Dual", cues=[cue])
        runner = SessionRunner(cuelist=cuelist, visual_director=mock_visual_director, audio_engine=mock_audio_engine)
        runner.start()

        # Expect second fade_in call (background) to force loop=True
        assert mock_audio_engine.fade_in_and_play.call_count == 2
        bg_call = mock_audio_engine.fade_in_and_play.call_args_list[1]
        assert bg_call.kwargs["loop"] is True

    def test_streaming_used_for_large_tracks(
        self,
        mock_visual_director,
        mock_audio_engine,
        tmp_path,
    ):
        """Large files are streamed via pygame.mixer.music to avoid OOM."""
        playback = tmp_path / "pb.json"
        playback.write_text('{"name":"PB"}')
        hypno = tmp_path / "hypno_large.wav"
        hypno.write_text("dummy")
        background = tmp_path / "bg.mp3"
        background.write_text("dummy")

        cue = Cue(
            name="Streamed Cue",
            duration_seconds=30,
            playback_pool=[PlaybackEntry(playback_path=playback, weight=1.0)],
            audio_tracks=[
                AudioTrack(file_path=hypno, volume=0.7, loop=False, role=AudioRole.HYPNO),
                AudioTrack(file_path=background, volume=0.4, loop=False, role=AudioRole.BACKGROUND),
            ],
        )

        cuelist = Cuelist(name="Streaming", cues=[cue])

        mock_audio_engine.should_stream.side_effect = lambda path: "hypno_large" in path
        mock_audio_engine.play_streaming_track.return_value = True

        runner = SessionRunner(cuelist=cuelist, visual_director=mock_visual_director, audio_engine=mock_audio_engine)
        runner.start()

        mock_audio_engine.play_streaming_track.assert_called_once()
        mock_audio_engine.load_channel.assert_any_call(0, str(background))

    def test_buffer_limit_enforces_streaming(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio,
    ):
        """Decoded-buffer cap forces streaming even when size threshold would cache."""
        mock_audio_engine.should_stream.return_value = False
        mock_audio_engine.play_streaming_track.return_value = True
        mock_audio_engine.estimate_track_duration.return_value = 45.0

        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine,
            session_data={"settings": {"audio": {"max_buffer_seconds_hypno": 10.0}}},
        )

        runner.start()

        mock_audio_engine.play_streaming_track.assert_called_once()
        mock_audio_engine.load_channel.assert_not_called()

    def test_streaming_track_stops_on_cue_end(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio,
    ):
        """Streaming audio receives fade-out when cue ends."""
        mock_audio_engine.should_stream.return_value = True
        mock_audio_engine.play_streaming_track.return_value = True

        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine,
        )
        runner.start()
        runner._end_cue()

        mock_audio_engine.stop_streaming_track.assert_called()

    def test_fade_transition_ends_old_cue_audio_channels(
        self,
        tmp_path,
    ):
        """FADE transitions must end old cue audio (e.g., looping Shepard) before starting next cue."""
        playback_dir = tmp_path / "playbacks"
        playback_dir.mkdir()

        playback1 = playback_dir / "test1.json"
        playback1.write_text('{"name": "Test 1"}')
        playback2 = playback_dir / "test2.json"
        playback2.write_text('{"name": "Test 2"}')

        cue1 = Cue(
            name="Cue 1",
            duration_seconds=1.0,
            playback_pool=[PlaybackEntry(playback_path=playback1, weight=1.0)],
        )
        cue2 = Cue(
            name="Cue 2",
            duration_seconds=1.0,
            playback_pool=[PlaybackEntry(playback_path=playback2, weight=1.0)],
        )

        cuelist = Cuelist(
            name="Fade Transition Test",
            cues=[cue1, cue2],
            transition_mode=CuelistTransitionMode.FADE,
            transition_duration_ms=250,
        )

        mock_visual_director = MagicMock()
        mock_visual_director.load_playback.return_value = True
        mock_visual_director.get_cycle_count.return_value = 0

        mock_audio_engine = MagicMock(spec=AudioEngine)
        mock_audio_engine.num_channels = 3
        mock_audio_engine.is_playing.side_effect = lambda ch: ch == 2
        mock_audio_engine.fade_out_and_stop.return_value = True
        mock_audio_engine.fade_in_and_play.return_value = True
        mock_audio_engine.load_channel.return_value = True
        mock_audio_engine.get_channel_length.return_value = 30.0
        mock_audio_engine.prefetch_tracks.return_value = {}
        mock_audio_engine.should_stream.return_value = False
        mock_audio_engine.play_streaming_track.return_value = False
        mock_audio_engine.stop_streaming_track.return_value = False
        mock_audio_engine.is_streaming_active.return_value = False
        mock_audio_engine.set_stream_threshold_mb.return_value = None
        mock_audio_engine.preload_sound.return_value = True
        mock_audio_engine.estimate_track_duration.return_value = 1.0
        mock_audio_engine.drop_cached_sound.return_value = None

        runner = SessionRunner(
            cuelist=cuelist,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine,
        )

        runner.start()
        mock_audio_engine.fade_out_and_stop.reset_mock()

        runner._execute_transition(1)

        # Old cue audio (channel 2) must be faded out when transition begins.
        mock_audio_engine.fade_out_and_stop.assert_called_once()
        assert mock_audio_engine.fade_out_and_stop.call_args.args[0] == 2

    def test_streaming_forced_when_channel_load_fails(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio,
    ):
        """SessionRunner retries via streaming when load_channel fails post-OOM."""
        mock_audio_engine.load_channel.return_value = False
        mock_audio_engine.should_stream.side_effect = [False, True]
        mock_audio_engine.play_streaming_track.return_value = True

        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine,
        )

        runner.start()

        mock_audio_engine.play_streaming_track.assert_called_once()

    def test_prefetch_deferred_until_buffer_available(
        self,
        mock_visual_director,
        mock_audio_engine,
        tmp_path,
    ):
        """Next cue waits to prefetch until active playback frees budget seconds."""
        playback = tmp_path / "pb.json"
        playback.write_text('{"name":"PB"}')
        hypno1 = tmp_path / "hypno1.mp3"
        hypno1.write_text("a")
        bg1 = tmp_path / "bg1.mp3"
        bg1.write_text("b")
        hypno2 = tmp_path / "hypno2.mp3"
        hypno2.write_text("c")
        bg2 = tmp_path / "bg2.mp3"
        bg2.write_text("d")

        cue1 = Cue(
            name="Cue 1",
            duration_seconds=20,
            playback_pool=[PlaybackEntry(playback_path=playback, weight=1.0)],
            audio_tracks=[
                AudioTrack(file_path=hypno1, role=AudioRole.HYPNO),
                AudioTrack(file_path=bg1, role=AudioRole.BACKGROUND),
            ],
        )
        cue2 = Cue(
            name="Cue 2",
            duration_seconds=20,
            playback_pool=[PlaybackEntry(playback_path=playback, weight=1.0)],
            audio_tracks=[
                AudioTrack(file_path=hypno2, role=AudioRole.HYPNO),
                AudioTrack(file_path=bg2, role=AudioRole.BACKGROUND),
            ],
        )

        cuelist = Cuelist(name="Deferred", cues=[cue1, cue2])

        mock_audio_engine.estimate_track_duration.return_value = 10.0

        runner = SessionRunner(
            cuelist=cuelist,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine,
            session_data={"settings": {"audio": {"max_buffer_seconds_hypno": 10.0, "max_buffer_seconds_background": 10.0}}},
        )
        runner.start()

        # Simulate being near the end of cue 0 so the lead window fires for cue 1
        runner._current_cue_index = 0
        runner._audio_prefetch_lead_seconds = 5.0
        runner._cue_start_time = time.time() - (cue1.duration_seconds - 4.0)
        runner._ensure_audio_prefetch_window()

        assert 1 in runner._prefetch_backlog
        initial_calls = mock_audio_engine.preload_sound.call_count

        runner._decay_active_audio_buffers(10.5)
        runner._retry_prefetch_backlog()

        assert mock_audio_engine.preload_sound.call_count > initial_calls
    
    def test_audio_cleanup_on_stop(
        self,
        mock_visual_director,
        mock_audio_engine,
        sample_cuelist_with_audio
    ):
        """All audio channels are stopped when session stops."""
        runner = SessionRunner(
            cuelist=sample_cuelist_with_audio,
            visual_director=mock_visual_director,
            audio_engine=mock_audio_engine
        )
        
        runner.start()
        runner.stop()
        
        # Verify stop_all was called
        mock_audio_engine.stop_all.assert_called_once()
    
    def test_audio_continues_without_audio_engine(
        self,
        mock_visual_director,
        sample_cuelist_with_audio
    ):
        """Session works without AudioEngine (audio_engine=None)."""
        runner = SessionRunner(
            sample_cuelist_with_audio,
            mock_visual_director,
            audio_engine=None  # No audio engine
        )
        
        # Should not crash
        runner.start()
        runner.update()
        runner.stop()
        
        assert runner.is_stopped()


class TestAudioFadeTiming:
    """Test audio fade timing accuracy."""
    
    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_fade_in_duration_passed_correctly(self, mock_mixer):
        """Fade-in duration is passed to pygame correctly."""
        engine = AudioEngine(num_channels=1)
        engine.init_ok = True
        
        mock_sound = MagicMock()
        mock_channel = MagicMock()
        mock_sound.play.return_value = mock_channel
        engine._sounds[0] = mock_sound
        
        engine.fade_in_and_play(0, fade_ms=2500, volume=0.9, loop=False)
        
        # Check that play was called with correct fade_ms
        mock_sound.play.assert_called_once_with(loops=0, fade_ms=2500)
    
    @patch('mesmerglass.engine.audio.pygame.mixer')
    def test_fade_out_duration_passed_correctly(self, mock_mixer):
        """Fade-out duration is passed to pygame correctly."""
        engine = AudioEngine(num_channels=1)
        engine.init_ok = True
        
        mock_channel = MagicMock()
        mock_channel.get_busy.return_value = True
        engine._channels[0] = mock_channel
        
        engine.fade_out_and_stop(0, fade_ms=1500)
        
        # Check that fadeout was called with correct duration
        mock_channel.fadeout.assert_called_once_with(1500)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
