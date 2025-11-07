"""Image and video loading with async caching.

Implements Trance-style media loading:
- Two-phase loading: decode to RAM (async) → upload to GPU (main thread)
- Image cache with LRU eviction
- Weighted shuffler to avoid repetition
- Support for images and video frames
"""

from __future__ import annotations
from dataclasses import dataclass
import os
import logging
from typing import Optional, List, Callable, Tuple
from pathlib import Path
import threading
import queue
from collections import deque
import numpy as np

try:
    from PIL import Image as PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

# Global media feature flags via environment
_NO_MEDIA = os.environ.get("MESMERGLASS_NO_MEDIA", "0") in ("1", "true", "True", "yes")
_DISABLE_OPENCV = os.environ.get("MESMERGLASS_DISABLE_OPENCV", "0") in ("1", "true", "True", "yes")

if _DISABLE_OPENCV and _HAS_CV2:
    # Soft-disable OpenCV usage to avoid native decoder crashes on some systems
    logging.getLogger(__name__).info("[media] MESMERGLASS_DISABLE_OPENCV=1 -> disabling OpenCV image loader")
    _HAS_CV2 = False


@dataclass(slots=True)
class ImageData:
    """Image data in RAM (not yet uploaded to GPU).
    
    Attributes:
        width: Image width in pixels
        height: Image height in pixels  
        data: RGBA pixel data as numpy array (height, width, 4) uint8
        path: Source file path
    """
    width: int
    height: int
    data: np.ndarray  # (height, width, 4) RGBA uint8
    path: Path
    
    def __post_init__(self):
        """Validate image data."""
        if self.data.dtype != np.uint8:
            raise ValueError("Image data must be uint8")
        if self.data.ndim != 3 or self.data.shape[2] != 4:
            raise ValueError("Image data must be (height, width, 4) RGBA")
        if self.data.shape[0] != self.height or self.data.shape[1] != self.width:
            raise ValueError(f"Image shape mismatch: {self.data.shape} vs ({self.height}, {self.width}, 4)")


@dataclass(slots=True)
class CachedImage:
    """Cached image with RAM and optional GPU state.
    
    Attributes:
        image_data: Decoded image in RAM
        gpu_texture_id: OpenGL texture ID (None if not uploaded yet)
        last_used: Access timestamp for LRU eviction
    """
    image_data: ImageData
    gpu_texture_id: Optional[int] = None
    last_used: float = 0.0


def load_image_sync(path: Path) -> Optional[ImageData]:
    """Load image from file synchronously.
    
    Tries OpenCV first (faster), falls back to PIL if available.
    
    Args:
        path: Path to image file
    
    Returns:
        ImageData if successful, None if failed
    """
    # Try OpenCV first (faster)
    if _HAS_CV2:
        try:
            # Load image with opencv (BGR format)
            img_bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            
            if img_bgr is None:
                raise ValueError(f"OpenCV failed to load {path}")
            
            # Convert BGR(A) to RGBA
            if len(img_bgr.shape) == 2:
                # Grayscale
                img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2RGBA)
            elif img_bgr.shape[2] == 3:
                # BGR → RGBA
                img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
            elif img_bgr.shape[2] == 4:
                # BGRA → RGBA
                img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGRA2RGBA)
            else:
                raise ValueError(f"Unexpected channel count: {img_bgr.shape[2]}")
            
            height, width = img_rgba.shape[:2]
            
            return ImageData(
                width=width,
                height=height,
                data=img_rgba,
                path=path
            )
        except Exception as e:
            # Fall through to PIL if opencv fails
            if not _HAS_PIL:
                return None
    
    # Fallback to PIL
    if _HAS_PIL:
        try:
            # Load image with PIL
            img = PILImage.open(path)
            
            # Convert to RGBA
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Convert to numpy array
            data = np.array(img, dtype=np.uint8)
            
            return ImageData(
                width=img.width,
                height=img.height,
                data=data,
                path=path
            )
        except Exception as e:
            return None
    
    return None


class AsyncImageLoader:
    """Async image loader that decodes images in background thread.
    
    Implements Trance's two-phase loading:
    1. Background thread: Decode image from disk → RAM
    2. Main thread: Upload RAM → GPU texture (on-demand)
    """
    
    def __init__(self, max_queue_size: int = 4):
        """Initialize async loader.
        
        Args:
            max_queue_size: Maximum pending load requests
        """
        self._load_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._result_queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """Start background loading thread."""
        if self._running:
            return
        if _NO_MEDIA:
            logging.getLogger(__name__).info("[media] NO_MEDIA=1 -> AsyncImageLoader not started")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """Stop background loading thread."""
        if not self._running:
            return
        
        self._running = False
        if self._thread:
            # Signal thread to stop
            try:
                self._load_queue.put(None, timeout=1.0)
            except queue.Full:
                pass
            self._thread.join(timeout=2.0)
            self._thread = None
    
    def request_load(self, path: Path) -> bool:
        """Request async load of image.
        
        Args:
            path: Path to image file
        
        Returns:
            True if request queued, False if queue full
        """
        if _NO_MEDIA:
            return False
        try:
            self._load_queue.put(path, block=False)
            return True
        except queue.Full:
            return False
    
    def get_loaded_image(self) -> Optional[Tuple[Path, Optional[ImageData]]]:
        """Get next loaded image from results.
        
        Returns:
            (path, image_data) tuple if available, None if no results
        """
        try:
            return self._result_queue.get(block=False)
        except queue.Empty:
            return None
    
    def _worker(self) -> None:
        """Background worker thread."""
        # Defensive: cap OpenCV threads to 1 inside worker to avoid oversubscription
        try:
            if _HAS_CV2:
                try:
                    cv2.setNumThreads(1)  # type: ignore[attr-defined]
                except Exception:
                    pass
        except Exception:
            pass
        while self._running:
            try:
                # Get next load request (blocking with timeout)
                path = self._load_queue.get(timeout=0.1)
                
                # None = stop signal
                if path is None:
                    break
                
                # Load image synchronously in background thread
                try:
                    logging.getLogger(__name__).info(f"[AsyncLoader] Starting load: {path}")
                    image_data = load_image_sync(path)
                    if image_data:
                        logging.getLogger(__name__).info(f"[AsyncLoader] Loaded successfully: {path} ({image_data.width}x{image_data.height})")
                    else:
                        logging.getLogger(__name__).warning(f"[AsyncLoader] Load returned None: {path}")
                except Exception as e:
                    # Catch-all to avoid propagating into native layer
                    logging.getLogger(__name__).warning(f"[media] load_image_sync crashed for {path}: {e}")
                    image_data = None
                
                # Put result in queue
                try:
                    self._result_queue.put((path, image_data), timeout=1.0)
                except queue.Full:
                    # Result queue full, discard oldest
                    try:
                        self._result_queue.get(block=False)
                    except queue.Empty:
                        pass
                    self._result_queue.put((path, image_data), timeout=1.0)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Async loader error: {e}")
                continue


class ImageCache:
    """LRU cache for images with async loading.
    
    Implements Trance ThemeBank image caching strategy:
    - Async decode from disk → RAM
    - On-demand upload RAM → GPU
    - LRU eviction when cache full
    - Configurable cache size per theme
    """
    
    def __init__(self, cache_size: int = 16):
        """Initialize image cache.
        
        Args:
            cache_size: Maximum cached images
        """
        self._cache_size = cache_size
        self._cache: dict[Path, CachedImage] = {}
        self._lru_order: deque[Path] = deque()
        self._loader = AsyncImageLoader()
        try:
            self._loader.start()
        except Exception as e:
            logging.getLogger(__name__).warning(f"[media] AsyncImageLoader start skipped: {e}")
    
    def __del__(self):
        """Cleanup on destruction."""
        self.shutdown()
    
    def shutdown(self) -> None:
        """Shutdown async loader."""
        self._loader.stop()
    
    def get_image(self, path: Path) -> Optional[ImageData]:
        """Get image from cache or load if not cached.
        
        Args:
            path: Path to image file
        
        Returns:
            ImageData if available, None if loading
        """
        import time
        
        # Check cache
        if path in self._cache:
            # Move to front of LRU
            try:
                self._lru_order.remove(path)
            except ValueError:
                pass
            self._lru_order.appendleft(path)
            
            # Update access time
            cached = self._cache[path]
            cached.last_used = time.time()
            return cached.image_data
        
        # Not in cache - request async load
        logger = logging.getLogger(__name__)
        success = self._loader.request_load(path)
        logger.info(f"[ImageCache] Requested async load: {path} (queued={success})")
        return None
    
    def process_loaded_images(self) -> int:
        """Process images that finished loading.
        
        Returns:
            Number of images added to cache
        """
        import time
        import logging
        logger = logging.getLogger(__name__)
        count = 0
        
        while True:
            result = self._loader.get_loaded_image()
            if result is None:
                break
            
            path, image_data = result
            if image_data is None:
                logger.warning(f"[ImageCache] Loaded image was None: {path}")
                continue
            
            logger.info(f"[ImageCache] Processing loaded image: {path} ({image_data.width}x{image_data.height})")
            
            # Add to cache
            if path not in self._cache:
                # Evict oldest if cache full
                while len(self._cache) >= self._cache_size:
                    if not self._lru_order:
                        break
                    oldest_path = self._lru_order.pop()
                    if oldest_path in self._cache:
                        del self._cache[oldest_path]
                
                # Add new image
                self._cache[path] = CachedImage(
                    image_data=image_data,
                    gpu_texture_id=None,
                    last_used=time.time()
                )
                self._lru_order.appendleft(path)
                count += 1
        
        return count
    
    def preload_images(self, paths: List[Path], max_count: Optional[int] = None) -> None:
        """Preload images into cache.
        
        Args:
            paths: List of image paths to preload
            max_count: Maximum images to preload (None = all)
        """
        for i, path in enumerate(paths):
            if max_count is not None and i >= max_count:
                break
            if path not in self._cache:
                self._loader.request_load(path)
    
    def clear(self) -> None:
        """Clear cache."""
        self._cache.clear()
        self._lru_order.clear()
    
    def get_cached_count(self) -> int:
        """Get number of cached images."""
        return len(self._cache)
    
    def get_texture_id(self, path: Path, upload_callback: Optional[Callable[[ImageData], int]] = None) -> Optional[int]:
        """Get GPU texture ID for image, uploading if needed.
        
        Args:
            path: Image file path
            upload_callback: Function to upload ImageData -> texture_id (None = skip upload)
        
        Returns:
            Texture ID if uploaded, None if not cached or not uploaded
        """
        if path not in self._cache:
            return None
        
        cached = self._cache[path]
        
        # Already uploaded?
        if cached.gpu_texture_id is not None:
            return cached.gpu_texture_id
        
        # Upload now if callback provided
        if upload_callback is not None:
            try:
                cached.gpu_texture_id = upload_callback(cached.image_data)
                return cached.gpu_texture_id
            except Exception as e:
                print(f"Failed to upload texture for {path}: {e}")
                return None
        
        return None
