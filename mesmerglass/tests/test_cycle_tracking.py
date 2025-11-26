"""Tests for Phase 2: Cycle Tracking and Event System.

Validates:
- VisualDirector cycle counter increments on media changes
- Cycle callbacks fire correctly
- Cycle tracking resets on new visual load
- CustomVisual cycle marker increments properly
- Session event system works correctly
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from mesmerglass.session.events import SessionEventType, SessionEvent, SessionEventEmitter


class TestSessionEventSystem:
    """Test session event emitter functionality."""
    
    def test_event_creation(self):
        """Test creating session events."""
        event = SessionEvent(SessionEventType.CUE_START)
        assert event.event_type == SessionEventType.CUE_START
        assert event.data is None
        assert event.timestamp is None
        
        event_with_data = SessionEvent(
            SessionEventType.CUE_START,
            data={"cue_index": 0, "cue_name": "Induction"}
        )
        assert event_with_data.data["cue_index"] == 0
        assert event_with_data.data["cue_name"] == "Induction"
    
    def test_event_string_representation(self):
        """Test event string conversion."""
        event = SessionEvent(SessionEventType.SESSION_START)
        assert "SESSION_START" in str(event)
        
        event_with_data = SessionEvent(
            SessionEventType.CUE_START,
            data={"cue_index": 0}
        )
        assert "CUE_START" in str(event_with_data)
        assert "cue_index=0" in str(event_with_data)
    
    def test_subscribe_and_emit(self):
        """Test subscribing to events and receiving emissions."""
        emitter = SessionEventEmitter()
        callback_data = []
        
        def callback(event: SessionEvent):
            callback_data.append(event)
        
        # Subscribe to CUE_START events
        emitter.subscribe(SessionEventType.CUE_START, callback)
        
        # Emit CUE_START event
        event = SessionEvent(SessionEventType.CUE_START, data={"cue_index": 0})
        emitter.emit(event)
        
        # Verify callback was called
        assert len(callback_data) == 1
        assert callback_data[0].event_type == SessionEventType.CUE_START
        assert callback_data[0].data["cue_index"] == 0
        assert callback_data[0].timestamp is not None  # Auto-added by emit
    
    def test_multiple_subscribers(self):
        """Test multiple subscribers to same event type."""
        emitter = SessionEventEmitter()
        callback1_calls = []
        callback2_calls = []
        
        def callback1(event: SessionEvent):
            callback1_calls.append(event)
        
        def callback2(event: SessionEvent):
            callback2_calls.append(event)
        
        # Both subscribe to same event type
        emitter.subscribe(SessionEventType.SESSION_START, callback1)
        emitter.subscribe(SessionEventType.SESSION_START, callback2)
        
        # Emit event
        event = SessionEvent(SessionEventType.SESSION_START)
        emitter.emit(event)
        
        # Both callbacks should be called
        assert len(callback1_calls) == 1
        assert len(callback2_calls) == 1
    
    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        emitter = SessionEventEmitter()
        callback_calls = []
        
        def callback(event: SessionEvent):
            callback_calls.append(event)
        
        # Subscribe and emit
        emitter.subscribe(SessionEventType.CUE_END, callback)
        emitter.emit(SessionEvent(SessionEventType.CUE_END))
        assert len(callback_calls) == 1
        
        # Unsubscribe and emit again
        emitter.unsubscribe(SessionEventType.CUE_END, callback)
        emitter.emit(SessionEvent(SessionEventType.CUE_END))
        assert len(callback_calls) == 1  # No new call
    
    def test_callback_error_handling(self):
        """Test that callback errors don't break emitter."""
        emitter = SessionEventEmitter()
        good_calls = []
        
        def bad_callback(event: SessionEvent):
            raise RuntimeError("Callback error!")
        
        def good_callback(event: SessionEvent):
            good_calls.append(event)
        
        # Subscribe both callbacks
        emitter.subscribe(SessionEventType.ERROR, bad_callback)
        emitter.subscribe(SessionEventType.ERROR, good_callback)
        
        # Emit event - bad callback should error but good callback should still run
        emitter.emit(SessionEvent(SessionEventType.ERROR))
        
        assert len(good_calls) == 1  # Good callback still executed
    
    def test_event_types_exist(self):
        """Test that all required event types are defined."""
        required_types = [
            'SESSION_START', 'SESSION_END', 'SESSION_PAUSE', 'SESSION_RESUME',
            'SESSION_STOP', 'CUE_START', 'CUE_END', 'TRANSITION_START',
            'TRANSITION_END', 'CUE_PROGRESS', 'ERROR'
        ]
        
        for type_name in required_types:
            assert hasattr(SessionEventType, type_name), f"Missing event type: {type_name}"


class TestCycleTracking:
    """Test cycle tracking in VisualDirector and CustomVisual.
    
    Note: These are integration-style tests that require the actual
    CustomVisual and VisualDirector classes. If those aren't available
    in test environment, these tests will be skipped.
    """
    
    @pytest.fixture
    def mock_playback_file(self, tmp_path):
        """Create a minimal valid playback file for testing."""
        playback = {
            "version": "1.0",
            "name": "Test Playback",
            "description": "Minimal playback for testing",
            "spiral": {
                "type": "logarithmic",
                "rotation_speed": 4.0,
                "opacity": 0.8,
                "intensity": 0.8,
                "reverse": False
            },
            "media": {
                "mode": "images",
                "cycle_speed": 50,
                "opacity": 1.0,
                "fade_duration": 0.5,
                "use_theme_bank": True,
                "paths": [],
                "shuffle": False
            },
            "text": {
                "enabled": False,
                "mode": "centered_sync",
                "opacity": 0.8,
                "use_theme_bank": True,
                "library": []
            },
            "zoom": {
                "mode": "none",
                "rate": 0.0
            }
        }
        
        import json
        playback_path = tmp_path / "test_playback.json"
        playback_path.write_text(json.dumps(playback, indent=2))
        return playback_path
    
    def test_custom_visual_cycle_marker(self, mock_playback_file):
        """Test that CustomVisual initializes and exposes cycle marker."""
        try:
            from mesmerglass.mesmerloom.custom_visual import CustomVisual
        except ImportError:
            pytest.skip("CustomVisual not available in test environment")
        
        # Create CustomVisual instance
        visual = CustomVisual(
            playback_path=mock_playback_file,
            theme_bank=None,
            on_change_image=None,
            on_change_video=None,
            on_rotate_spiral=None,
            compositor=None,
            text_director=None
        )
        
        # Check initial state
        assert hasattr(visual, '_cycle_marker')
        assert visual._cycle_marker == 0
        assert hasattr(visual, 'get_current_cycle')
        assert visual.get_current_cycle() == 0
        
        # Simulate media change by incrementing marker
        visual._cycle_marker += 1
        assert visual.get_current_cycle() == 1
        
        # Test reset
        visual.reset()
        assert visual.get_current_cycle() == 0
    
    def test_visual_director_cycle_tracking_init(self):
        """Test that VisualDirector initializes cycle tracking."""
        try:
            from mesmerglass.mesmerloom.visual_director import VisualDirector
        except ImportError:
            pytest.skip("VisualDirector not available in test environment")
        
        director = VisualDirector(theme_bank=None, video_streamer=None, compositor=None)
        
        # Check cycle tracking attributes
        assert hasattr(director, '_cycle_count')
        assert hasattr(director, '_last_cycle_marker')
        assert hasattr(director, '_cycle_callbacks')
        assert director._cycle_count == 0
        assert director._last_cycle_marker == 0
        assert director._cycle_callbacks == []
    
    def test_visual_director_callback_registration(self):
        """Test registering and unregistering cycle callbacks."""
        try:
            from mesmerglass.mesmerloom.visual_director import VisualDirector
        except ImportError:
            pytest.skip("VisualDirector not available in test environment")
        
        director = VisualDirector(theme_bank=None, video_streamer=None, compositor=None)
        callback_calls = []
        
        def callback():
            callback_calls.append(1)
        
        # Register callback
        director.register_cycle_callback(callback)
        assert len(director._cycle_callbacks) == 1
        assert callback in director._cycle_callbacks
        
        # Unregister callback
        director.unregister_cycle_callback(callback)
        assert len(director._cycle_callbacks) == 0
        assert callback not in director._cycle_callbacks
    
    def test_cycle_boundary_detection(self, mock_playback_file):
        """Test that cycle boundary detection increments counter and fires callbacks."""
        try:
            from mesmerglass.mesmerloom.visual_director import VisualDirector
            from mesmerglass.mesmerloom.custom_visual import CustomVisual
        except ImportError:
            pytest.skip("Required classes not available in test environment")
        
        director = VisualDirector(theme_bank=None, video_streamer=None, compositor=None)
        callback_calls = []
        
        def callback():
            callback_calls.append(director.get_cycle_count())
        
        director.register_cycle_callback(callback)
        
        # Load a custom visual
        visual = CustomVisual(
            playback_path=mock_playback_file,
            theme_bank=None,
            on_change_image=None,
            on_change_video=None,
            on_rotate_spiral=None,
            compositor=None,
            text_director=None
        )
        director.current_visual = visual
        
        # Initial state
        assert director.get_cycle_count() == 0
        
        # Simulate media change (increment visual's cycle marker)
        visual._cycle_marker = 1
        director._check_cycle_boundary()
        
        # Cycle count should increment and callback should fire
        assert director.get_cycle_count() == 1
        assert len(callback_calls) == 1
        assert callback_calls[0] == 1
        
        # Another cycle
        visual._cycle_marker = 2
        director._check_cycle_boundary()
        
        assert director.get_cycle_count() == 2
        assert len(callback_calls) == 2
        assert callback_calls[1] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
