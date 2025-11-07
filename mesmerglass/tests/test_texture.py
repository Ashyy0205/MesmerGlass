"""Tests for GPU texture management."""

import pytest
import numpy as np
from pathlib import Path

from mesmerglass.content.media import ImageData
from mesmerglass.content.texture import (
    upload_image_to_gpu, delete_texture, get_texture_info,
    TextureManager, bind_texture, unbind_texture, TextureUploadError
)


@pytest.fixture
def gl_widget(qtbot):
    """Create OpenGL widget for testing."""
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from PyQt6.QtGui import QSurfaceFormat
    
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    
    class TestWidget(QOpenGLWidget):
        def __init__(self):
            super().__init__()
            self.initialized = False
        
        def initializeGL(self):
            self.initialized = True
    
    widget = TestWidget()
    widget.show()
    qtbot.addWidget(widget)
    qtbot.waitExposed(widget)
    
    assert widget.initialized, "OpenGL not initialized"
    widget.makeCurrent()
    
    yield widget
    
    widget.close()


@pytest.fixture
def test_image():
    """Create test ImageData."""
    data = np.zeros((128, 128, 4), dtype=np.uint8)
    data[:, :, 0] = 255  # Red channel
    data[:, :, 3] = 255  # Alpha channel
    
    return ImageData(
        width=128,
        height=128,
        data=data,
        path=Path("test.png")
    )


def test_upload_texture(gl_widget, test_image):
    """Test uploading single texture."""
    texture_id = upload_image_to_gpu(test_image)
    
    assert texture_id > 0, "Should return valid texture ID"
    
    # Verify texture properties
    info = get_texture_info(texture_id)
    assert info['width'] == 128
    assert info['height'] == 128
    
    # Cleanup
    delete_texture(texture_id)


def test_upload_with_existing_id(gl_widget, test_image):
    """Test uploading to existing texture ID."""
    # Create first texture
    texture_id = upload_image_to_gpu(test_image)
    
    # Upload different image to same ID
    test_image.data[:, :, 0] = 0
    test_image.data[:, :, 2] = 255  # Blue instead of red
    
    same_id = upload_image_to_gpu(test_image, texture_id=texture_id)
    assert same_id == texture_id, "Should reuse same texture ID"
    
    delete_texture(texture_id)


def test_upload_without_mipmaps(gl_widget, test_image):
    """Test uploading without mipmaps."""
    texture_id = upload_image_to_gpu(test_image, generate_mipmaps=False)
    
    assert texture_id > 0
    delete_texture(texture_id)


def test_upload_nearest_filtering(gl_widget, test_image):
    """Test uploading with nearest filtering."""
    texture_id = upload_image_to_gpu(test_image, filter_linear=False)
    
    assert texture_id > 0
    delete_texture(texture_id)


def test_bind_unbind(gl_widget, test_image):
    """Test binding and unbinding texture."""
    texture_id = upload_image_to_gpu(test_image)
    
    # Should not raise
    bind_texture(texture_id, texture_unit=0)
    unbind_texture(texture_unit=0)
    
    # Test different texture unit
    bind_texture(texture_id, texture_unit=1)
    unbind_texture(texture_unit=1)
    
    delete_texture(texture_id)


def test_get_texture_info(gl_widget, test_image):
    """Test getting texture information."""
    texture_id = upload_image_to_gpu(test_image)
    
    info = get_texture_info(texture_id)
    
    assert 'texture_id' in info
    assert 'width' in info
    assert 'height' in info
    assert 'internal_format' in info
    
    assert info['width'] == 128
    assert info['height'] == 128
    
    delete_texture(texture_id)


def test_texture_manager_upload(gl_widget, test_image):
    """Test TextureManager upload."""
    manager = TextureManager()
    
    texture_id = manager.get_or_upload(test_image)
    assert texture_id > 0
    
    # Should cache
    cached_id = manager.get_or_upload(test_image)
    assert cached_id == texture_id, "Should return cached texture"
    
    # Stats
    stats = manager.get_stats()
    assert stats['texture_count'] == 1
    
    manager.clear()


def test_texture_manager_multiple(gl_widget):
    """Test TextureManager with multiple textures."""
    manager = TextureManager()
    
    # Create 3 different images
    images = []
    for i in range(3):
        data = np.zeros((64, 64, 4), dtype=np.uint8)
        data[:, :, i % 3] = 255  # Different color per image
        data[:, :, 3] = 255
        
        img = ImageData(
            width=64,
            height=64,
            data=data,
            path=Path(f"test_{i}.png")
        )
        images.append(img)
    
    # Upload all
    texture_ids = []
    for img in images:
        tid = manager.get_or_upload(img)
        texture_ids.append(tid)
    
    # Verify all different
    assert len(set(texture_ids)) == 3, "Should create unique textures"
    
    # Stats
    stats = manager.get_stats()
    assert stats['texture_count'] == 3
    
    manager.clear()


def test_texture_manager_delete(gl_widget, test_image):
    """Test TextureManager delete."""
    manager = TextureManager()
    
    texture_id = manager.get_or_upload(test_image)
    
    # Verify it's in cache
    stats = manager.get_stats()
    assert stats['texture_count'] == 1
    
    # Delete by path
    manager.delete(test_image.path)
    
    # Should be removed from cache
    stats = manager.get_stats()
    assert stats['texture_count'] == 0
    
    # Should upload again (may reuse same GL texture ID, that's ok)
    new_id = manager.get_or_upload(test_image)
    assert new_id > 0, "Should successfully upload after delete"
    
    # Should be back in cache
    stats = manager.get_stats()
    assert stats['texture_count'] == 1
    
    manager.clear()


def test_texture_manager_clear(gl_widget, test_image):
    """Test TextureManager clear."""
    manager = TextureManager()
    
    # Upload texture
    manager.get_or_upload(test_image)
    
    stats = manager.get_stats()
    assert stats['texture_count'] == 1
    
    # Clear
    manager.clear()
    
    stats = manager.get_stats()
    assert stats['texture_count'] == 0
    
    # Should be able to upload again
    texture_id = manager.get_or_upload(test_image)
    assert texture_id > 0


def test_invalid_image_data(gl_widget):
    """Test uploading invalid image data."""
    # Wrong dtype
    data = np.zeros((64, 64, 4), dtype=np.float32)  # Should be uint8
    
    with pytest.raises(ValueError, match="uint8"):
        ImageData(width=64, height=64, data=data, path=Path("test.png"))
    
    # Wrong shape
    data = np.zeros((64, 64, 3), dtype=np.uint8)  # Should be 4 channels
    
    with pytest.raises(ValueError, match="RGBA"):
        ImageData(width=64, height=64, data=data, path=Path("test.png"))
