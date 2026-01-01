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
import time
from typing import Optional, List, Callable, Tuple, Any
from pathlib import Path
import threading
import queue
from collections import deque
import numpy as np
from ..logging_utils import BurstSampler, PerfTracer

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


def _perf_span(
    tracer: Optional[PerfTracer],
    name: str,
    *,
    category: str = "media",
    metadata: Optional[dict[str, Any]] = None,
):
    if tracer is None:
        return PerfTracer.noop_span()
    meta = dict(metadata or {})
    return tracer.span(name, category=category, metadata=meta)


def load_image_sync(path: Path, perf_tracer: Optional[PerfTracer] = None) -> Optional[ImageData]:
    """Load image from file synchronously with optional PerfTracer spans."""

    span = _perf_span(perf_tracer, "media_load_image", metadata={"path": path.name})
    backend = None
    error: Optional[str] = None
    start = time.perf_counter()
    image: Optional[ImageData] = None

    with span:
        if _HAS_CV2:
            try:
                img_bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                if img_bgr is None:
                    raise ValueError(f"OpenCV failed to load {path}")

                if len(img_bgr.shape) == 2:
                    img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2RGBA)
                elif img_bgr.shape[2] == 3:
                    img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
                elif img_bgr.shape[2] == 4:
                    img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGRA2RGBA)
                else:
                    raise ValueError(f"Unexpected channel count: {img_bgr.shape[2]}")

                height, width = img_rgba.shape[:2]
                image = ImageData(width=width, height=height, data=img_rgba, path=path)
                backend = "opencv"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                if not _HAS_PIL:
                    span.annotate(result="fail", backend="opencv", error=error)
                    return None

        if image is None and _HAS_PIL:
            try:
                img = PILImage.open(path)
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                data = np.array(img, dtype=np.uint8)
                image = ImageData(width=img.width, height=img.height, data=data, path=path)
                backend = "pil"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

        duration_ms = (time.perf_counter() - start) * 1000.0
        if image is not None:
            span.annotate(
                result="ok",
                backend=backend or "unknown",
                width=image.width,
                height=image.height,
                duration_ms=round(duration_ms, 3),
            )
        else:
            span.annotate(result="fail", backend=backend or "none", error=error or "unknown", duration_ms=round(duration_ms, 3))

    return image


class AsyncImageLoader:
    """Async image loader that decodes images in background thread.
    
    Implements Trance's two-phase loading:
    1. Background thread: Decode image from disk → RAM
    2. Main thread: Upload RAM → GPU texture (on-demand)
    """
    
    def __init__(
        self,
        max_queue_size: int = 4,
        throttle_sleep: float = 0.0,
        *,
        perf_tracer: Optional[PerfTracer] = None,
        name: str = "async_loader",
    ):
        """Initialize async loader.
        
        Args:
            max_queue_size: Maximum pending load requests
        """
        self._load_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._result_queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._throttle_sleep = max(0.0, float(throttle_sleep))
        self._stats_sampler = BurstSampler(interval_s=2.0)
        self._stats_success = 0
        self._stats_failed = 0
        self._perf = perf_tracer
        self._perf_name = name

    def _perf_span(self, name: str, *, metadata: Optional[dict[str, Any]] = None):
        if self._perf is None:
            return PerfTracer.noop_span()
        meta = {"loader": self._perf_name}
        if metadata:
            meta.update(metadata)
        return self._perf.span(name, category="media", metadata=meta)
    
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

    def pending(self) -> int:
        """Return approximate queue depth for diagnostics."""

        try:
            return self._load_queue.qsize()
        except Exception:
            return 0
    
    def request_load(self, path: Path) -> bool:
        """Request async load of image.
        
        Args:
            path: Path to image file
        
        Returns:
            True if request queued, False if queue full
        """
        if _NO_MEDIA:
            return False
        span = self._perf_span("media_queue_request", metadata={"path": path.name})
        with span:
            try:
                self._load_queue.put(path, block=False)
                depth = self._load_queue.qsize()
                span.annotate(result="queued", queue_depth=depth)
                return True
            except queue.Full:
                depth = self._load_queue.qsize() if hasattr(self._load_queue, "qsize") else -1
                span.annotate(result="full", queue_depth=depth)
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

    def _record_loader_stats(self, success: bool) -> None:
        """Update counters and emit a summary INFO line when the sampler fires."""

        if success:
            self._stats_success += 1
        else:
            self._stats_failed += 1

        processed = self._stats_sampler.record()
        if not processed:
            return

        logger = logging.getLogger(__name__)
        success_count = self._stats_success
        failure_count = self._stats_failed
        self._stats_success = 0
        self._stats_failed = 0
        try:
            queue_depth = self._load_queue.qsize()
        except Exception:
            queue_depth = -1

        logger.info(
            "[AsyncLoader] Processed %d image(s) in last %.1fs (ok=%d, failed=%d, queue=%d)",
            processed,
            self._stats_sampler.interval_s,
            success_count,
            failure_count,
            queue_depth,
        )
    
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
                wait_span = self._perf_span("media_queue_wait")
                with wait_span:
                    path = self._load_queue.get(timeout=0.1)
                
                # None = stop signal
                if path is None:
                    break
                
                # Load image synchronously in background thread
                decode_span = self._perf_span("media_async_decode", metadata={"path": getattr(path, "name", str(path))})
                with decode_span:
                    try:
                        logging.getLogger(__name__).debug(f"[AsyncLoader] Starting load: {path}")
                        image_data = load_image_sync(path, perf_tracer=self._perf)
                        if image_data:
                            logging.getLogger(__name__).debug(
                                f"[AsyncLoader] Loaded successfully: {path} ({image_data.width}x{image_data.height})"
                            )
                            decode_span.annotate(result="ok", width=image_data.width, height=image_data.height)
                        else:
                            logging.getLogger(__name__).warning(f"[AsyncLoader] Load returned None: {path}")
                            decode_span.annotate(result="none")
                    except Exception as e:
                        # Catch-all to avoid propagating into native layer
                        logging.getLogger(__name__).warning(f"[media] load_image_sync crashed for {path}: {e}")
                        decode_span.annotate(result="error", error=str(e))
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

                if self._throttle_sleep > 0:
                    time.sleep(self._throttle_sleep)

                self._record_loader_stats(image_data is not None)
                
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
    
    def __init__(
        self,
        cache_size: int = 16,
        loader_queue_size: int = 4,
        loader_throttle_ms: float = 0.0,
        perf_tracer: Optional[PerfTracer] = None,
        cache_name: Optional[str] = None,
    ):
        """Initialize image cache.
        
        Args:
            cache_size: Maximum cached images
        """
        self._cache_size = cache_size
        self._cache: dict[Path, CachedImage] = {}
        self._lru_order: deque[Path] = deque()
        self._lock = threading.RLock()
        throttle_sec = max(0.0, loader_throttle_ms) / 1000.0
        self._perf = perf_tracer
        self._perf_name = cache_name or "image_cache"
        self._loader = AsyncImageLoader(
            max_queue_size=loader_queue_size,
            throttle_sleep=throttle_sec,
            perf_tracer=perf_tracer,
            name=f"{self._perf_name}:loader",
        )
        try:
            self._loader.start()
        except Exception as e:
            logging.getLogger(__name__).warning(f"[media] AsyncImageLoader start skipped: {e}")

    def _perf_span(self, name: str, *, metadata: Optional[dict[str, Any]] = None):
        if self._perf is None:
            return PerfTracer.noop_span()
        meta = {"cache": self._perf_name}
        if metadata:
            meta.update(metadata)
        return self._perf.span(name, category="media", metadata=meta)
    
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
        with self._lock:
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
        logger.debug(f"[ImageCache] Requested async load: {path} (queued={success})")
        return None

    def peek_cached(self, path: Path) -> Optional[ImageData]:
        """Return cached image data without requesting a load."""
        with self._lock:
            cached = self._cache.get(path)
            return cached.image_data if cached else None

    def add_preloaded_image(
        self,
        path: Path,
        image_data: ImageData,
        *,
        on_evict_texture_id: Optional[Callable[[int], None]] = None,
    ) -> bool:
        """Insert a decoded image into the cache (used by ThemeBank background preload).

        Returns:
            True if inserted, False if already present.
        """

        evicted_texture_ids: list[int] = []
        with self._lock:
            if path in self._cache:
                return False

            while len(self._cache) >= self._cache_size:
                if not self._lru_order:
                    break
                oldest_path = self._lru_order.pop()
                evicted_item = self._cache.pop(oldest_path, None)
                if evicted_item and evicted_item.gpu_texture_id is not None:
                    evicted_texture_ids.append(evicted_item.gpu_texture_id)

            self._cache[path] = CachedImage(
                image_data=image_data,
                gpu_texture_id=None,
                last_used=time.time(),
            )
            self._lru_order.appendleft(path)

        if on_evict_texture_id:
            for texture_id in evicted_texture_ids:
                try:
                    on_evict_texture_id(int(texture_id))
                except Exception:
                    continue

        return True
    
    def process_loaded_images(self, *, max_items: int = 8) -> int:
        """Process images that finished loading.
        
        Returns:
            Number of images added to cache
        """
        import time
        import logging
        logger = logging.getLogger(__name__)
        count = 0
        
        max_items = max(0, int(max_items))
        while True:
            if max_items and count >= max_items:
                break
            result = self._loader.get_loaded_image()
            if result is None:
                break
            
            path, image_data = result
            span = self._perf_span("media_cache_ingest", metadata={"path": path.name})
            with span:
                if image_data is None:
                    logger.warning(f"[ImageCache] Loaded image was None: {path}")
                    span.annotate(result="none")
                    continue
                
                logger.debug(f"[ImageCache] Processing loaded image: {path} ({image_data.width}x{image_data.height})")

                evicted_texture_ids: list[int] = []
                with self._lock:
                    if path not in self._cache:
                        evicted = 0
                        while len(self._cache) >= self._cache_size:
                            if not self._lru_order:
                                break
                            oldest_path = self._lru_order.pop()
                            evicted_item = self._cache.pop(oldest_path, None)
                            if evicted_item and evicted_item.gpu_texture_id is not None:
                                evicted_texture_ids.append(evicted_item.gpu_texture_id)
                            if evicted_item:
                                evicted += 1

                        self._cache[path] = CachedImage(
                            image_data=image_data,
                            gpu_texture_id=None,
                            last_used=time.time(),
                        )
                        self._lru_order.appendleft(path)
                        count += 1
                        span.annotate(
                            result="cached",
                            cache_fill=len(self._cache),
                            cache_limit=self._cache_size,
                            evicted=evicted,
                        )
                    else:
                        span.annotate(result="duplicate")

                if evicted_texture_ids:
                    from .texture import delete_texture

                    for texture_id in evicted_texture_ids:
                        try:
                            delete_texture(texture_id)
                        except Exception:
                            continue
        
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
            with self._lock:
                in_cache = path in self._cache
            if not in_cache:
                self._loader.request_load(path)
    
    def clear(self) -> None:
        """Clear cache."""
        # CRITICAL: Release all GPU textures before clearing!
        from .texture import delete_texture
        for cached in self._cache.values():
            if cached.gpu_texture_id is not None:
                delete_texture(cached.gpu_texture_id)
        
        self._cache.clear()
        self._lru_order.clear()
    
    def get_cached_count(self) -> int:
        """Get number of cached images."""
        return len(self._cache)

    def pending_loads(self) -> int:
        """Get number of queued async decode requests."""

        loader = getattr(self, "_loader", None)
        if not loader:
            return 0
        try:
            return loader.pending()
        except Exception:
            return 0
    
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
