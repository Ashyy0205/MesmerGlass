"""GPU texture management for image rendering.

Handles uploading ImageData to OpenGL textures for compositor rendering.
"""

from __future__ import annotations
from typing import Optional
from pathlib import Path
import logging

try:
    import OpenGL.GL as GL
    _HAS_OPENGL = True
except ImportError:
    _HAS_OPENGL = False

from .media import ImageData


logger = logging.getLogger(__name__)


class TextureUploadError(Exception):
    """Error during texture upload."""
    pass


def upload_image_to_gpu(
    image_data: ImageData,
    texture_id: Optional[int] = None,
    generate_mipmaps: bool = True,
    filter_linear: bool = True
) -> int:
    """Upload ImageData to OpenGL texture.
    
    Args:
        image_data: Decoded image in RAM (RGBA uint8)
        texture_id: Existing texture ID to reuse, or None to generate new
        generate_mipmaps: Generate mipmaps for better quality at distance
        filter_linear: Use linear filtering (True) or nearest (False)
    
    Returns:
        OpenGL texture ID
    
    Raises:
        TextureUploadError: If OpenGL not available or upload fails
    """
    if not _HAS_OPENGL:
        raise TextureUploadError("OpenGL not available")
    
    try:
        # Generate new texture if needed
        if texture_id is None:
            texture_id = GL.glGenTextures(1)
        
        # Bind texture
        GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
        
        # Set texture parameters
        if filter_linear:
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, 
                             GL.GL_LINEAR_MIPMAP_LINEAR if generate_mipmaps else GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        else:
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        
        # Wrap mode: clamp to edge (no repeating)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        
        # Upload pixel data (RGBA8)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D,      # target
            0,                      # level (base mipmap)
            GL.GL_RGBA8,           # internal format
            image_data.width,       # width
            image_data.height,      # height
            0,                      # border (must be 0)
            GL.GL_RGBA,            # format
            GL.GL_UNSIGNED_BYTE,   # type
            image_data.data        # pixel data
        )
        
        # Generate mipmaps
        if generate_mipmaps:
            GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
        
        # Unbind
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        
        # Log success (handle both str and Path for image_data.path)
        path_str = str(image_data.path) if hasattr(image_data.path, '__str__') else 'unknown'
        logger.debug(f"Uploaded texture {texture_id}: {image_data.width}x{image_data.height} from {path_str}")
        
        return texture_id
        
    except Exception as e:
        raise TextureUploadError(f"Failed to upload texture: {e}") from e


def delete_texture(texture_id: int) -> None:
    """Delete OpenGL texture.
    
    Args:
        texture_id: OpenGL texture ID to delete
    """
    if not _HAS_OPENGL:
        return
    
    try:
        GL.glDeleteTextures([texture_id])
        logger.debug(f"Deleted texture {texture_id}")
    except Exception as e:
        logger.warning(f"Failed to delete texture {texture_id}: {e}")


def bind_texture(texture_id: int, texture_unit: int = 0) -> None:
    """Bind texture for rendering.
    
    Args:
        texture_id: OpenGL texture ID
        texture_unit: Texture unit (0-31, default 0)
    """
    if not _HAS_OPENGL:
        return
    
    GL.glActiveTexture(GL.GL_TEXTURE0 + texture_unit)
    GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)


def unbind_texture(texture_unit: int = 0) -> None:
    """Unbind texture.
    
    Args:
        texture_unit: Texture unit to unbind (0-31, default 0)
    """
    if not _HAS_OPENGL:
        return
    
    GL.glActiveTexture(GL.GL_TEXTURE0 + texture_unit)
    GL.glBindTexture(GL.GL_TEXTURE_2D, 0)


def get_texture_info(texture_id: int) -> dict:
    """Get texture information (for debugging).
    
    Args:
        texture_id: OpenGL texture ID
    
    Returns:
        Dictionary with texture properties
    """
    if not _HAS_OPENGL:
        return {}
    
    try:
        GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
        
        width = GL.glGetTexLevelParameteriv(GL.GL_TEXTURE_2D, 0, GL.GL_TEXTURE_WIDTH)
        height = GL.glGetTexLevelParameteriv(GL.GL_TEXTURE_2D, 0, GL.GL_TEXTURE_HEIGHT)
        internal_format = GL.glGetTexLevelParameteriv(GL.GL_TEXTURE_2D, 0, GL.GL_TEXTURE_INTERNAL_FORMAT)
        
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        
        return {
            'texture_id': texture_id,
            'width': width,
            'height': height,
            'internal_format': internal_format,
        }
    except Exception as e:
        logger.warning(f"Failed to get texture info for {texture_id}: {e}")
        return {}


class TextureManager:
    """Manages texture lifecycle and GPU uploads.
    
    Integrates with ImageCache to handle on-demand GPU uploads.
    """
    
    def __init__(self):
        """Initialize texture manager."""
        self._textures: dict[Path, int] = {}  # path -> texture_id
        self._texture_info: dict[int, dict] = {}  # texture_id -> metadata
    
    def get_or_upload(self, image_data: ImageData) -> int:
        """Get existing texture or upload new one.
        
        Args:
            image_data: Image to upload
        
        Returns:
            OpenGL texture ID
        """
        path = image_data.path
        
        # Check if already uploaded
        if path in self._textures:
            texture_id = self._textures[path]
            logger.debug(f"Texture cache hit: {path.name} -> {texture_id}")
            return texture_id
        
        # Upload new texture
        texture_id = upload_image_to_gpu(image_data)
        self._textures[path] = texture_id
        self._texture_info[texture_id] = {
            'path': path,
            'width': image_data.width,
            'height': image_data.height,
        }
        
        logger.info(f"Uploaded new texture: {path.name} -> {texture_id} ({image_data.width}x{image_data.height})")
        return texture_id
    
    def delete(self, path: Path) -> None:
        """Delete texture by path.
        
        Args:
            path: Image file path
        """
        if path in self._textures:
            texture_id = self._textures.pop(path)
            self._texture_info.pop(texture_id, None)
            delete_texture(texture_id)
            logger.info(f"Deleted texture: {path.name} (ID {texture_id})")
    
    def clear(self) -> None:
        """Delete all textures."""
        for texture_id in list(self._textures.values()):
            delete_texture(texture_id)
        
        count = len(self._textures)
        self._textures.clear()
        self._texture_info.clear()
        logger.info(f"Cleared {count} textures")
    
    def get_stats(self) -> dict:
        """Get texture manager statistics.
        
        Returns:
            Dictionary with stats
        """
        return {
            'texture_count': len(self._textures),
            'textures': list(self._texture_info.values()),
        }
