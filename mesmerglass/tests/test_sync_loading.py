"""
Simple test to verify synchronous loading eliminates delays.

Just checks that with synchronous loading enabled, ThemeBank.get_image()
returns images immediately without returning None.
"""
from pathlib import Path
from unittest.mock import Mock, patch
import time

import pytest

from mesmerglass.content.themebank import ThemeBank
from mesmerglass.content.theme import ThemeConfig


@pytest.mark.parametrize("num_requests", [10, 50, 100])
def test_synchronous_loading_no_delays(tmp_path, num_requests):
    """
    Test that synchronous loading returns images immediately without None returns.
    
    With synchronous loading, every call to get_image() should return an image
    data immediately - no None returns that require retries.
    """
    # Mock the image loading to return instantly
    mock_image_data = Mock()
    mock_image_data.width = 1920
    mock_image_data.height = 1080
    
    # Create mock theme
    theme1 = ThemeConfig(
        name="Test Theme 1",
        image_path=[Path(f"test_image{i}.jpg") for i in range(50)],
        enabled=True
    )
    
    with patch('mesmerglass.content.media.load_image_sync', return_value=mock_image_data):
        # Create ThemeBank
        theme_bank = ThemeBank(themes=[theme1], root_path=tmp_path)
        
        # Set active theme (1-indexed like Trance)
        theme_bank.set_active_themes(primary_index=1)
        
        # Request images rapidly
        none_count = 0
        success_count = 0
        
        for i in range(num_requests):
            result = theme_bank.get_image(alternate=False)
            
            if result is None:
                none_count += 1
            else:
                success_count += 1
        
        # With synchronous loading, ALL requests should succeed immediately
        assert none_count == 0, \
            f"Expected zero None returns (instant loading), but got {none_count}/{num_requests} failures"
        
        assert success_count == num_requests, \
            f"Expected all {num_requests} requests to succeed, but only {success_count} did"
        
        print(f"\n✓ Synchronous loading test passed:")
        print(f"  - {num_requests} rapid requests")
        print(f"  - {success_count} immediate successes")
        print(f"  - {none_count} delays (expected: 0)")


def test_synchronous_loading_timing_benchmark(tmp_path):
    """
    Benchmark synchronous loading to ensure it's fast enough for 60fps.
    
    At 60fps with 3-frame cycles (speed 100), we have ~50ms per cycle.
    Synchronous loading should complete in <10ms to be acceptable.
    """
    import time
    
    mock_image_data = Mock()
    mock_image_data.width = 1920
    mock_image_data.height = 1080
    
    # Create mock theme with 100 images
    theme1 = ThemeConfig(
        name="Timing Test Theme",
        image_path=[Path(f"test_image{i}.jpg") for i in range(100)],
        enabled=True
    )
    
    with patch('mesmerglass.content.media.load_image_sync', return_value=mock_image_data):
        theme_bank = ThemeBank(themes=[theme1], root_path=tmp_path)
        
        # Set active theme (1-indexed like Trance)
        theme_bank.set_active_themes(primary_index=1)
        
        # Time 100 consecutive loads
        start = time.perf_counter()
        
        for i in range(100):
            result = theme_bank.get_image(alternate=False)
            assert result is not None, f"Load {i} failed"
        
        elapsed = time.perf_counter() - start
        avg_time_ms = (elapsed / 100) * 1000
        
        print(f"\n✓ Timing benchmark:")
        print(f"  - 100 loads in {elapsed:.3f}s")
        print(f"  - Average: {avg_time_ms:.2f}ms per load")
        print(f"  - 60fps budget: 16.67ms per frame")
        
        # Should be fast enough for real-time playback
        assert avg_time_ms < 10, \
            f"Synchronous loading too slow: {avg_time_ms:.2f}ms (max 10ms for 60fps)"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
