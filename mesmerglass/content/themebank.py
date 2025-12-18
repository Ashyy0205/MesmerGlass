"""Theme bank - manages multiple themes with media selection.

Implements Trance ThemeBank algorithm:
- Keeps 2 active themes loaded
- Loads 3rd theme asynchronously in background
- Weighted shuffler avoids last 8 selected images
- Theme switching with cooldown
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple, Sequence
from pathlib import Path
from collections import deque
import random
from dataclasses import dataclass
import time
import threading
import gc
import os
import logging

from ..logging_utils import BurstSampler, PerfTracer

from .theme import ThemeConfig, Shuffler
from .media import ImageCache, ImageData


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThemeBankStatus:
    """Lightweight snapshot of ThemeBank readiness for diagnostics/CLI."""

    themes_total: int
    active_primary: Optional[int]
    active_alternate: Optional[int]
    total_images: int
    total_videos: int
    cached_images: int
    pending_loads: int
    ready: bool
    ready_reason: str
    last_image_path: Optional[str]
    last_video_path: Optional[str]


@dataclass(frozen=True)
class ThemeBankThrottleConfig:
    """Configurable throttles for ThemeBank background work."""

    preload_aggressively: bool = False
    lookahead_count: int = 32
    lookahead_batch_size: int = 12
    lookahead_sleep_ms: float = 4.0
    max_preload_ms: float = 200.0
    loader_queue_size: int = 8
    sync_warning_ms: float = 45.0
    background_warning_ms: float = 150.0

    @classmethod
    def from_env(cls) -> "ThemeBankThrottleConfig":
        """Build config from MESMERGLASS_THEME_* environment overrides."""

        def _read(name: str, cast, default):
            raw = os.environ.get(name)
            if raw is None:
                return default
            try:
                return cast(raw)
            except Exception:
                return default

        def _read_bool(name: str, default: bool) -> bool:
            raw = os.environ.get(name)
            if raw is None:
                return default
            raw_lower = raw.strip().lower()
            if raw_lower in {"1", "true", "yes", "on"}:
                return True
            if raw_lower in {"0", "false", "no", "off"}:
                return False
            return default

        return cls(
            preload_aggressively=_read_bool("MESMERGLASS_THEME_PRELOAD_ALL", cls.preload_aggressively),
            lookahead_count=max(0, int(_read("MESMERGLASS_THEME_LOOKAHEAD", int, cls.lookahead_count))),
            lookahead_batch_size=max(0, int(_read("MESMERGLASS_THEME_BATCH", int, cls.lookahead_batch_size))),
            lookahead_sleep_ms=max(0.0, float(_read("MESMERGLASS_THEME_SLEEP_MS", float, cls.lookahead_sleep_ms))),
            max_preload_ms=max(0.0, float(_read("MESMERGLASS_THEME_MAX_MS", float, cls.max_preload_ms))),
            loader_queue_size=max(1, int(_read("MESMERGLASS_MEDIA_QUEUE", int, cls.loader_queue_size))),
            sync_warning_ms=max(1.0, float(_read("MESMERGLASS_THEME_SYNC_WARN_MS", float, cls.sync_warning_ms))),
            background_warning_ms=max(1.0, float(_read("MESMERGLASS_THEME_BG_WARN_MS", float, cls.background_warning_ms))),
        )

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ThemeBankThrottleConfig":
        """Create config from session/settings dict."""
        base = cls.from_env()
        if not data:
            return base

        def _coerce_bool(value: Any, default: bool) -> bool:
            if value is None:
                return default
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"1", "true", "yes", "on"}:
                    return True
                if lowered in {"0", "false", "no", "off"}:
                    return False
                return default
            return bool(value)

        return cls(
            preload_aggressively=_coerce_bool(data.get("preload_aggressively"), base.preload_aggressively),
            lookahead_count=max(0, int(data.get("lookahead_count", base.lookahead_count))),
            lookahead_batch_size=max(0, int(data.get("lookahead_batch_size", base.lookahead_batch_size))),
            lookahead_sleep_ms=max(0.0, float(data.get("lookahead_sleep_ms", base.lookahead_sleep_ms))),
            max_preload_ms=max(0.0, float(data.get("max_preload_ms", base.max_preload_ms))),
            loader_queue_size=max(1, int(data.get("loader_queue_size", base.loader_queue_size))),
            sync_warning_ms=max(1.0, float(data.get("sync_warning_ms", base.sync_warning_ms))),
            background_warning_ms=max(1.0, float(data.get("background_warning_ms", base.background_warning_ms))),
        )


class ThemeBank:
    """Manages multiple themes and media selection.
    
    Implements Trance ThemeBank strategy:
    - Theme 0: Previous theme (being unloaded)
    - Theme 1: Primary active theme  
    - Theme 2: Alternate active theme
    - Theme 3: Next theme (loading in background)
    """
    
    # Number of recent images to track
    LAST_IMAGE_COUNT = 100  # Increased to avoid repetition with large image sets
    LAST_VIDEO_COUNT = 40
    
    # Cooldown between theme switches (in async updates, ~8-10 seconds)
    THEME_SWITCH_COOLDOWN = 500
    
    def __init__(
        self,
        themes: List[ThemeConfig],
        root_path: Path,
        image_cache_size: int = 64,
        throttle_config: Optional[ThemeBankThrottleConfig] = None,
        perf_tracer: Optional[PerfTracer] = None,
    ):
        """Initialize theme bank.
        
        Args:
            themes: List of theme configurations
            root_path: Root directory for resolving paths
            image_cache_size: Total images to cache across all themes
        """
        self._themes = [t for t in themes if t.enabled]
        self._root_path = root_path
        self._image_cache_size = image_cache_size
        self._throttle = throttle_config or ThemeBankThrottleConfig.from_env()
        self._perf = perf_tracer
        
        # Active theme indices (None = not loaded)
        self._active_theme_indices = [None, None, None, None]  # 0=old, 1=primary, 2=alt, 3=next
        
        # Image caches per theme
        self._image_caches: dict[int, ImageCache] = {}
        
        # Shufflers per theme to avoid repetition
        self._shufflers: dict[int, Shuffler] = {}
        self._video_shufflers: dict[int, Shuffler] = {}
        
        # Track last selected images globally (avoid repetition)
        self._last_images: deque[tuple[int, int]] = deque(maxlen=self.LAST_IMAGE_COUNT)
        self._last_videos: deque[tuple[int, int]] = deque(maxlen=self.LAST_VIDEO_COUNT)
        
        # Theme switch cooldown
        self._last_theme_switch = 0
        self._async_update_count = 0
        
        # Aggressive preloading for fast cycling (eliminates all loading delays)
        # Preload as many images as possible into RAM
        # RECOMMENDED MEDIA POOL SIZES:
        # - 8GB RAM:  ~100-150 images (1-2 MP each)
        # - 16GB RAM: ~200-300 images (1-2 MP each)
        # - 32GB RAM: ~400-500 images (1-2 MP each)
        # - 64GB RAM: ~800-1000 images (1-2 MP each)
        # Large images (>5MP) should be avoided or downscaled
        
        self._preload_aggressively = self._throttle.preload_aggressively
        self._cache_refill_interval = 5  # Check every N frames to keep cache full
        self._last_cache_refill = 0  # Track when we last refilled cache

        # Lookahead preloading throttle
        self._lookahead_counter = 0  # Count get_image calls
        self._lookahead_interval = 1  # Run lookahead EVERY get_image call (aggressive for real-time cycling)
        self._lookahead_count = max(0, self._throttle.lookahead_count)
        self._lookahead_batch_size = max(0, self._throttle.lookahead_batch_size)
        self._lookahead_sleep_sec = max(0.0, self._throttle.lookahead_sleep_ms) / 1000.0
        self._max_preload_ms = max(0.0, self._throttle.max_preload_ms)
        self._sync_warning_ms = max(1.0, self._throttle.sync_warning_ms)
        self._background_warning_ms = max(1.0, self._throttle.background_warning_ms)
        self._base_batch_size = self._lookahead_batch_size
        self._base_sleep_sec = self._lookahead_sleep_sec
        self._adaptive_batch_size = self._base_batch_size
        self._adaptive_sleep_sec = self._base_sleep_sec
        self._slow_preload_strikes = 0
        
        # Background preload thread management
        self._preload_thread: Optional[threading.Thread] = None
        self._preload_lock = threading.Lock()
        self._preloading_in_progress = False
        
        # Garbage collection throttle (only collect every N evictions to avoid blocking)
        self._eviction_count = 0
        self._gc_interval = 50  # Collect garbage every 50 evictions

        # Diagnostics
        self._last_image_path: Optional[str] = None
        self._last_video_path: Optional[str] = None

        # Flag when any network-backed media directories are in use so
        # callers can adjust readiness timeouts for slower scans.
        self.network_sources_detected: bool = False
        
        # Preload images for theme paths
        self._preload_theme_images()

        self._image_stats_sampler = BurstSampler(interval_s=2.0)
        self._image_stats_window = {"served": 0, "sync": 0, "slow": 0}

        # Font media support (Phase 8)
        self._font_library: list[str] = []
        self._font_queue: deque[str] = deque()
        self._last_font_choice: Optional[str] = None

        logger.info(
            "[ThemeBank] throttle: preload=%s lookahead=%d batch=%d sleep=%.2fms max_ms=%.1f queue=%d",
            self._preload_aggressively,
            self._lookahead_count,
            self._lookahead_batch_size,
            self._throttle.lookahead_sleep_ms,
            self._max_preload_ms,
            self._throttle.loader_queue_size,
        )
    
    # ===== Font Library Support =====

    def set_font_library(self, fonts: Sequence[str]) -> None:
        """Replace the font media pool and rebuild the shuffle queue."""

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in fonts or []:
            if not raw:
                continue
            try:
                candidate = str(Path(raw).resolve())
            except Exception:
                candidate = str(raw)
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(candidate)

        self._font_library = normalized
        self._last_font_choice = None
        self._rebuild_font_queue()
        logger.debug("[ThemeBank] Font library updated: %d font(s)", len(normalized))

    def pick_font_for_playback(self, *, consume: bool = True) -> Optional[str]:
        """Return the next font path to use for text overlays."""

        if not self._font_library:
            return None

        if not self._font_queue:
            self._rebuild_font_queue()

        if not self._font_queue:
            return None

        selected = self._font_queue[0] if not consume else self._font_queue.popleft()
        self._last_font_choice = selected
        return selected

    def _rebuild_font_queue(self) -> None:
        if not self._font_library:
            self._font_queue.clear()
            return

        shuffled = self._font_library[:]
        random.shuffle(shuffled)
        self._font_queue.clear()
        self._font_queue.extend(shuffled)

    # ===== Diagnostics Helpers =====

    def _normalized_path(self, path_str: str) -> Path:
        path = Path(path_str)
        return path if path.is_absolute() else self._root_path / path

    def _has_accessible_media(self, *, media_type: str) -> bool:
        attr = "image_path" if media_type == "image" else "animation_path"
        for theme in self._themes:
            media_list = getattr(theme, attr, [])
            for raw_path in media_list:
                try:
                    candidate = self._normalized_path(raw_path)
                except Exception:
                    continue
                if candidate.exists():
                    return True
        return False

    def _collect_cache_stats(self) -> Tuple[int, int]:
        cached = 0
        pending = 0
        for cache in self._image_caches.values():
            try:
                cached += cache.get_cached_count()
                pending += cache.pending_loads()
            except Exception:
                continue
        return cached, pending

    def get_status(self) -> ThemeBankStatus:
        """Return a snapshot describing media readiness."""

        total_images = sum(len(theme.image_path) for theme in self._themes)
        total_videos = sum(len(theme.animation_path) for theme in self._themes)
        cached_images, pending_loads = self._collect_cache_stats()
        primary_idx = self._active_theme_indices[1]
        alt_idx = self._active_theme_indices[2]
        ready = total_images > 0 and self._has_accessible_media(media_type="image")
        reason = "OK" if ready else "No accessible image files"
        status = ThemeBankStatus(
            themes_total=len(self._themes),
            active_primary=primary_idx,
            active_alternate=alt_idx,
            total_images=total_images,
            total_videos=total_videos,
            cached_images=cached_images,
            pending_loads=pending_loads,
            ready=ready,
            ready_reason=reason,
            last_image_path=self._last_image_path,
            last_video_path=self._last_video_path,
        )
        return status

    def ensure_ready(
        self,
        *,
        require_videos: bool = False,
        timeout_s: float = 0.0,
    ) -> ThemeBankStatus:
        """Spin until media is available or timeout expires."""

        deadline = time.time() + max(0.0, timeout_s)
        status = self.get_status()
        need_videos = require_videos

        def _is_ready(candidate: ThemeBankStatus) -> bool:
            if not candidate.ready:
                return False
            if need_videos and candidate.total_videos <= 0:
                return False
            return True

        while True:
            if _is_ready(status):
                return status
            if time.time() >= deadline:
                return status
            # Keep async loaders moving to populate caches
            try:
                self.async_update()
            except Exception:
                pass
            time.sleep(0.05)
            status = self.get_status()

    def _preload_theme_images(self) -> None:
        """Build media structures (image caches + video shufflers) for each theme."""
        for i, theme in enumerate(self._themes):
            image_count = len(theme.image_path)
            video_count = len(theme.animation_path)

            if image_count > 0:
                span = self._perf_span(
                    "theme_init_preload",
                    metadata={"theme": theme.name, "theme_index": i, "images": image_count},
                )
                with span:
                    # Create/refresh shuffler
                    self._shufflers[i] = Shuffler(image_count)

                    # Create image cache
                    cache_size = self._cache_per_theme()
                    # Shutdown an old cache if we are rebuilding sizes
                    old_cache = self._image_caches.get(i)
                    if old_cache:
                        try:
                            old_cache.shutdown()
                        except Exception:
                            pass
                    self._image_caches[i] = ImageCache(
                        cache_size=cache_size,
                        loader_queue_size=self._throttle.loader_queue_size,
                        perf_tracer=self._perf,
                        cache_name=f"theme:{theme.name}",
                    )

                    # Resolve full paths (handle both relative and absolute paths)
                    full_paths = []
                    for path_str in theme.image_path:
                        path = Path(path_str)
                        if path.is_absolute():
                            full_paths.append(path)
                        else:
                            full_paths.append(self._root_path / path)

                    # Aggressively preload images to eliminate loading delays
                    preload_count = cache_size if self._preload_aggressively else min(15, cache_size)
                    self._image_caches[i].preload_images(full_paths, max_count=preload_count)

                    if self._preload_aggressively:
                        self._preload_initial_lookahead(i)

                    span.annotate(cache_size=cache_size, preload_count=preload_count)
                    logger.info(
                        f"[ThemeBank] Theme '{theme.name}': {image_count} images, preloading {preload_count} into cache"
                    )
            else:
                # Remove stale image data structures when theme no longer has images
                if i in self._shufflers:
                    self._shufflers.pop(i, None)
                cache = self._image_caches.pop(i, None)
                if cache:
                    try:
                        cache.shutdown()
                    except Exception:
                        pass

            if video_count > 0:
                self._video_shufflers[i] = Shuffler(video_count)
                logger.info(
                    f"[ThemeBank] Theme '{theme.name}': {video_count} videos ready for selection"
                )
            else:
                self._video_shufflers.pop(i, None)
    
    def _cache_per_theme(self) -> int:
        """Calculate cache size per theme.
        
        Uses the full cache size from initialization (default 256).
        With 100-image lookahead preloading, larger cache = smoother playback.
        
        Returns:
            Images to cache per theme
        """
        if not self._themes:
            return self._image_cache_size  # Use full cache size from init (default 256)
        
        # Use full cache size from initialization (default 256)
        total_cache = self._image_cache_size
        
        # Split cache among themes if multiple active
        cache_per_theme = total_cache // max(1, len(self._themes))
        
        # For single-theme scenarios, use full cache
        max_images = max(len(theme.image_path) for theme in self._themes)
        if len(self._themes) == 1:
            return min(max_images, total_cache)
        else:
            return min(max_images, cache_per_theme)

    def _emit_image_stats(self, cache: Optional[ImageCache]) -> None:
        """Summarize recent image activity to avoid per-call INFO spam."""

        served = self._image_stats_window.get("served", 0)
        if served <= 0:
            return
        sync = self._image_stats_window.get("sync", 0)
        slow = self._image_stats_window.get("slow", 0)
        cache_fill = len(getattr(cache, "_cache", {})) if cache is not None else 0
        cache_limit = getattr(cache, "_cache_size", 0) if cache is not None else 0
        logger.info(
            "[ThemeBank] served %d images (sync=%d slow_sync=%d) cache=%d/%d",
            served,
            sync,
            slow,
            cache_fill,
            cache_limit,
        )
        self._image_stats_window = {"served": 0, "sync": 0, "slow": 0}

    def _perf_span(
        self,
        name: str,
        *,
        category: str = "themebank",
        metadata: Optional[dict[str, Any]] = None,
    ) -> object:
        tracer = self._perf
        if tracer is None:
            return PerfTracer.noop_span()
        return tracer.span(name, category=category, metadata=metadata or {})

    def get_perf_snapshot(self, *, reset: bool = False) -> Optional[dict[str, Any]]:
        """Expose PerfTracer snapshots for CLI diagnostics."""

        if self._perf is None:
            return None
        return self._perf.consume() if reset else self._perf.snapshot()

    def set_active_themes(self, primary_index: int, alt_index: Optional[int] = None) -> None:
        """Set active themes.
        
        Args:
            primary_index: Index of primary theme (1-indexed like Trance)
            alt_index: Optional index of alternate theme
        """
        # Convert from 1-indexed to 0-indexed
        primary_idx = primary_index - 1
        alt_idx = (alt_index - 1) if alt_index is not None else None
        
        if primary_idx < 0 or primary_idx >= len(self._themes):
            raise ValueError(f"Invalid primary theme index: {primary_index}")
        if alt_idx is not None and (alt_idx < 0 or alt_idx >= len(self._themes)):
            raise ValueError(f"Invalid alternate theme index: {alt_index}")
        
        self._active_theme_indices[1] = primary_idx
        self._active_theme_indices[2] = alt_idx
    
    def get_image(self, alternate: bool = False) -> Optional[ImageData]:
        """Get next image from active theme.
        
        Args:
            alternate: If True, use alternate theme; otherwise primary
        
        Returns:
            ImageData if available, None if no images
        """
        verbose = logger.isEnabledFor(logging.DEBUG)
        
        # Select theme
        theme_slot = 2 if alternate else 1
        theme_idx = self._active_theme_indices[theme_slot]
        if verbose:
            logger.debug(
                "[ThemeBank] get_image alt=%s slot=%s indices=%s",
                alternate,
                theme_slot,
                self._active_theme_indices,
            )
        
        if theme_idx is None:
            logger.warning(f"[ThemeBank] No active theme at slot {theme_slot}")
            return None
        
        theme = self._themes[theme_idx]
        if not theme.image_path:
            logger.warning(f"[ThemeBank] Theme {theme_idx} has no image paths")
            return None
        
        if verbose:
            logger.debug(f"[ThemeBank] Theme {theme_idx} has {len(theme.image_path)} images")
        
        # Get cache for this theme
        cache = self._image_caches.get(theme_idx)
        if cache is None:
            logger.warning(f"[ThemeBank] No image cache for theme {theme_idx}")
            return None
        
        # Get shuffler
        shuffler = self._shufflers.get(theme_idx)
        if shuffler is None:
            logger.warning(f"[ThemeBank] No shuffler for theme {theme_idx}")
            return None

        span = self._perf_span(
            "theme_get_image",
            metadata={
                "theme": theme.name,
                "theme_slot": theme_slot,
                "alternate": alternate,
                "theme_idx": theme_idx,
            },
        )
        source = "cache"
        with span:
            # Process any newly loaded images before touching the cache
            cache.process_loaded_images()

            # Select next image using weighted shuffler
            image_index = shuffler.next()
            if verbose:
                logger.debug(f"[ThemeBank] Shuffler selected image index: {image_index}")

            if image_index >= len(theme.image_path):
                logger.warning(f"[ThemeBank] Image index {image_index} >= {len(theme.image_path)}")
                span.annotate(error="index_oob", requested=image_index, total=len(theme.image_path))
                return None

            # Handle both relative and absolute paths
            path_str = theme.image_path[image_index]
            image_path = Path(path_str) if Path(path_str).is_absolute() else self._root_path / path_str
            self._last_image_path = str(image_path)

            if verbose:
                logger.debug(f"[ThemeBank] Loading image: {image_path}")

            # Try to get from cache first
            image_data = cache.get_image(image_path)
            if image_data is None:
                source = "sync"
                if verbose:
                    logger.debug("[ThemeBank] Image cache miss; loading synchronously")
                load_start = time.perf_counter()
                self._image_stats_window["sync"] += 1

                sync_span = self._perf_span(
                    "theme_sync_load",
                    metadata={"theme": theme.name, "path": image_path.name},
                )
                with sync_span:
                    from .media import load_image_sync

                    image_data = load_image_sync(image_path, perf_tracer=self._perf)
                    load_duration = (time.perf_counter() - load_start) * 1000.0
                    slow = load_duration > self._sync_warning_ms
                    if slow:
                        self._image_stats_window["slow"] += 1
                        logger.warning(
                            f"[perf] SLOW sync load: {load_duration:.2f}ms for {image_path.name}"
                            + (
                                f" ({image_data.width}x{image_data.height} px)"
                                if image_data is not None
                                else ""
                            )
                        )
                    sync_span.annotate(result="ok" if image_data else "fail", slow=slow)

                if image_data is not None:
                    # EVICT oldest if cache is full (LRU) - enforce cache limit!
                    while len(cache._cache) >= cache._cache_size:
                        if not cache._lru_order:
                            break
                        oldest_path = cache._lru_order.pop()
                        if oldest_path in cache._cache:
                            evicted_item = cache._cache[oldest_path]
                            if hasattr(evicted_item, "gpu_texture_id") and evicted_item.gpu_texture_id is not None:
                                from .texture import delete_texture

                                delete_texture(evicted_item.gpu_texture_id)
                                logger.debug(
                                    f"[ThemeBank] Released GPU texture {evicted_item.gpu_texture_id} for {oldest_path.name}"
                                )

                            del cache._cache[oldest_path]
                            logger.debug(
                                f"[ThemeBank] Evicted {oldest_path.name} from cache (limit: {cache._cache_size})"
                            )
                            self._eviction_count += 1

                    if self._eviction_count >= self._gc_interval:
                        gc.collect()
                        self._eviction_count = 0

                    cache._cache[image_path] = type(
                        "obj",
                        (object,),
                        {
                            "image_data": image_data,
                            "gpu_texture_id": None,
                        },
                    )()
                    cache._lru_order.appendleft(image_path)
                    if verbose:
                        logger.debug(
                            "[ThemeBank] Sync load %sx%s cache=%d/%d",
                            image_data.width,
                            image_data.height,
                            len(cache._cache),
                            cache._cache_size,
                        )
                else:
                    logger.warning(f"[ThemeBank] Synchronous load failed for {image_path}")
                    span.annotate(error="sync_failed")
                    return None

            if verbose and image_data is not None:
                logger.debug(f"[ThemeBank] Loaded image: {image_data.width}x{image_data.height}")

            # LOOKAHEAD PRELOADING: Load next 15 images in background
            self._lookahead_counter += 1
            if self._lookahead_counter >= self._lookahead_interval:
                self._lookahead_counter = 0
                self._preload_lookahead(theme_idx, shuffler, cache, current_index=image_index)

            self._last_images.append((theme_idx, image_index))
            shuffler.decrease(image_index)

            if len(self._last_images) >= self.LAST_IMAGE_COUNT:
                old_theme_idx, old_image_idx = self._last_images[0]
                old_shuffler = self._shufflers.get(old_theme_idx)
                if old_shuffler:
                    old_shuffler.increase(old_image_idx)

            self._image_stats_window["served"] += 1
            if self._image_stats_sampler.record():
                self._emit_image_stats(cache)

            span.annotate(
                result="ok",
                source=source,
                cache_fill=len(cache._cache),
                cache_limit=cache._cache_size,
                image_index=image_index,
            )
            return image_data

    def get_video(self, alternate: bool = False) -> Optional[Path]:
        """Get next video path, falling back to any theme that has animations."""
        preferred_slot = 2 if alternate else 1
        candidates = self._video_theme_candidates(preferred_slot)

        if not candidates:
            logger.warning("[ThemeBank] No themes available for video selection")
            return None

        preferred_idx = self._active_theme_indices[preferred_slot] if 0 <= preferred_slot < len(self._active_theme_indices) else None

        for theme_idx in candidates:
            video_path = self._pick_video_from_theme(theme_idx)
            if video_path is not None:
                if preferred_idx is None:
                    logger.info(
                        "[ThemeBank] Video fallback using theme '%s' (preferred slot empty)",
                        self._themes[theme_idx].name,
                    )
                elif theme_idx != preferred_idx:
                    logger.info(
                        "[ThemeBank] Video fallback: theme '%s' has no videos, using '%s'",
                        self._themes[preferred_idx].name,
                        self._themes[theme_idx].name,
                    )
                return video_path

        logger.warning("[ThemeBank] No videos available across all themes")
        return None

    def _video_theme_candidates(self, preferred_slot: int) -> list[int]:
        """Order themes to try for video playback."""
        candidates: list[int] = []
        seen: set[int] = set()

        def add(index: Optional[int]) -> None:
            if index is None or index in seen:
                return
            seen.add(index)
            candidates.append(index)

        # Preferred slot (primary or alternate requested)
        if 0 <= preferred_slot < len(self._active_theme_indices):
            add(self._active_theme_indices[preferred_slot])

        # Prefer the other display slot next (primary vs alternate)
        if preferred_slot in (1, 2):
            other_slot = 1 if preferred_slot == 2 else 2
            add(self._active_theme_indices[other_slot])

        # Remaining active slots (old/next themes)
        for slot_idx, theme_idx in enumerate(self._active_theme_indices):
            if slot_idx == preferred_slot:
                continue
            add(theme_idx)

        # Finally, consider every theme in order
        for idx in range(len(self._themes)):
            add(idx)

        return candidates

    def _pick_video_from_theme(self, theme_idx: int) -> Optional[Path]:
        """Select a video from a specific theme, updating history/shufflers."""
        if theme_idx < 0 or theme_idx >= len(self._themes):
            return None

        theme = self._themes[theme_idx]
        if not theme.animation_path:
            return None

        shuffler = self._video_shufflers.get(theme_idx)
        if shuffler is None or shuffler._count != len(theme.animation_path):
            shuffler = Shuffler(len(theme.animation_path))
            self._video_shufflers[theme_idx] = shuffler

        try:
            video_index = shuffler.next()
        except ValueError:
            return None

        if video_index >= len(theme.animation_path):
            logger.warning(
                "[ThemeBank] Video index %d out of range for theme %s",
                video_index,
                theme.name,
            )
            return None

        path_str = theme.animation_path[video_index]
        video_path = Path(path_str) if Path(path_str).is_absolute() else self._root_path / path_str

        if len(self._last_videos) >= self._last_videos.maxlen:
            old_theme_idx, old_index = self._last_videos.popleft()
            old_shuffler = self._video_shufflers.get(old_theme_idx)
            if old_shuffler:
                old_shuffler.increase(old_index)

        self._last_videos.append((theme_idx, video_index))
        shuffler.decrease(video_index)

        logger.debug("[ThemeBank] Selected video %s from theme '%s'", video_path, theme.name)
        self._last_video_path = str(video_path)
        return video_path
    
    def _preload_lookahead_async(self, theme_idx: int, shuffler: 'Shuffler', cache: 'ImageCache') -> None:
        """Background thread worker for preloading images.
        
        Runs in a separate thread to avoid blocking the main thread during
        large preload operations.
        """
        try:
            theme = self._themes[theme_idx]
            lookahead_count = self._lookahead_count
            if lookahead_count <= 0 or self._lookahead_batch_size <= 0:
                return

            span = self._perf_span(
                "theme_background_preload",
                metadata={
                    "theme": theme.name,
                    "theme_idx": theme_idx,
                    "requested": lookahead_count,
                    "batch": self._lookahead_batch_size,
                },
            )

            preload_start = time.perf_counter()
            # Get EXACT next indices from shuffler's deterministic queue (100% accurate!)
            next_indices = shuffler.peek_next(lookahead_count)
            batch_limit = self._lookahead_batch_size if self._lookahead_batch_size > 0 else len(next_indices)
            if self._adaptive_batch_size and self._adaptive_batch_size > 0:
                batch_limit = min(batch_limit, self._adaptive_batch_size)
            batch_limit = min(batch_limit, len(next_indices))
            sleep_interval = self._adaptive_sleep_sec if self._adaptive_sleep_sec > 0 else self._lookahead_sleep_sec
            
            preloaded = 0
            with span:
                for idx in next_indices:
                    if idx >= len(theme.image_path):
                        continue
                    
                    path_str = theme.image_path[idx]
                    image_path = Path(path_str) if Path(path_str).is_absolute() else self._root_path / path_str
                    
                    if cache.get_image(image_path) is not None:
                        continue
                    
                    from .media import load_image_sync

                    image_data = load_image_sync(image_path, perf_tracer=self._perf)
                    if image_data is not None:
                        with self._preload_lock:
                            while len(cache._cache) >= cache._cache_size:
                                if not cache._lru_order:
                                    break
                                oldest_path = cache._lru_order.pop()
                                if oldest_path in cache._cache:
                                    evicted_item = cache._cache[oldest_path]
                                    if hasattr(evicted_item, 'gpu_texture_id') and evicted_item.gpu_texture_id is not None:
                                        from .texture import delete_texture

                                        delete_texture(evicted_item.gpu_texture_id)
                                    
                                    del cache._cache[oldest_path]
                                    self._eviction_count += 1
                            
                            if self._eviction_count >= self._gc_interval:
                                gc.collect()
                                self._eviction_count = 0
                            
                            cache._cache[image_path] = type('obj', (object,), {
                                'image_data': image_data,
                                'gpu_texture_id': None
                            })()
                            cache._lru_order.appendleft(image_path)
                            preloaded += 1

                    elapsed_ms = (time.perf_counter() - preload_start) * 1000.0
                    if batch_limit and preloaded >= batch_limit:
                        break
                    if self._max_preload_ms and elapsed_ms >= self._max_preload_ms:
                        break
                    if sleep_interval > 0:
                        time.sleep(sleep_interval)
                
                if preloaded > 0:
                    preload_duration = (time.perf_counter() - preload_start) * 1000.0
                    logger.info(
                        f"[ThemeBank] Background preloaded {preloaded}/{lookahead_count} items in {preload_duration:.2f}ms (cache: {len(cache._cache)}/{cache._cache_size}, limit enforced: {len(cache._cache) <= cache._cache_size})"
                    )
                    if preload_duration > self._background_warning_ms:
                        logger.warning(
                            f"[perf] SLOW background preload: {preload_duration:.2f}ms (loaded {preloaded} images)"
                        )
                    self._apply_preload_adaptive_feedback(preload_duration, preloaded)
                span.annotate(preloaded=preloaded, cache_fill=len(cache._cache), cache_limit=cache._cache_size)
        finally:
            with self._preload_lock:
                self._preloading_in_progress = False

    def _apply_preload_adaptive_feedback(self, duration_ms: float, preloaded: int) -> None:
        """Adjust background preload aggressiveness based on runtime."""

        if self._base_batch_size <= 2:
            self._adaptive_batch_size = self._base_batch_size
            self._adaptive_sleep_sec = self._base_sleep_sec
            return

        slow = duration_ms > self._background_warning_ms
        fast = duration_ms < (self._background_warning_ms * 0.6)
        prev_batch = self._adaptive_batch_size or self._base_batch_size
        prev_sleep = self._adaptive_sleep_sec

        if slow:
            self._slow_preload_strikes = min(5, self._slow_preload_strikes + 1)
            new_batch = max(2, int(prev_batch * 0.75)) if prev_batch > 0 else prev_batch
            new_batch = min(new_batch, self._base_batch_size)
            new_sleep = min(self._base_sleep_sec + 0.05, prev_sleep + 0.002) if prev_sleep >= 0 else prev_sleep

            if new_batch != self._adaptive_batch_size or abs(new_sleep - self._adaptive_sleep_sec) > 1e-9:
                logger.warning(
                    "[perf] ThemeBank auto-throttle: batch=%d->%d sleep=%.1f->%.1fms (duration=%.1fms)",
                    self._adaptive_batch_size,
                    new_batch,
                    self._adaptive_sleep_sec * 1000.0,
                    new_sleep * 1000.0,
                    duration_ms,
                )
            self._adaptive_batch_size = new_batch
            self._adaptive_sleep_sec = new_sleep
            return

        if self._adaptive_batch_size >= self._base_batch_size and self._adaptive_sleep_sec <= self._base_sleep_sec:
            self._slow_preload_strikes = max(0, self._slow_preload_strikes - 1)
            return

        if fast and preloaded > 0:
            self._slow_preload_strikes = max(0, self._slow_preload_strikes - 1)
            new_batch = min(self._base_batch_size, self._adaptive_batch_size + 2)
            new_sleep = max(self._base_sleep_sec, self._adaptive_sleep_sec - 0.001)

            if new_batch != self._adaptive_batch_size or abs(new_sleep - self._adaptive_sleep_sec) > 1e-9:
                logger.info(
                    "[perf] ThemeBank throttle relaxed: batch=%d->%d sleep=%.1f->%.1fms",
                    self._adaptive_batch_size,
                    new_batch,
                    self._adaptive_sleep_sec * 1000.0,
                    new_sleep * 1000.0,
                )
            self._adaptive_batch_size = new_batch
            self._adaptive_sleep_sec = new_sleep
    
    def _preload_lookahead(self, theme_idx: int, shuffler: 'Shuffler', cache: 'ImageCache', current_index: int) -> None:
        """Preload next N EXACT images in the shuffle sequence.
        
        Uses shuffler.peek_next() to get the EXACT next items from the deterministic queue.
        This ensures 100% accurate prediction and efficient preloading.
        
        Now runs in a background thread to avoid blocking during queue regeneration.
        
        Args:
            theme_idx: Theme index
            shuffler: Shuffler for this theme
            cache: Image cache for this theme
            current_index: Current image index just loaded (unused, kept for API compatibility)
        """
        # Don't start a new preload if one is already running or throttled off
        with self._preload_lock:
            if self._preloading_in_progress or self._lookahead_count <= 0 or self._lookahead_batch_size <= 0:
                return
            self._preloading_in_progress = True
        
        # Start background preload thread
        self._preload_thread = threading.Thread(
            target=self._preload_lookahead_async,
            args=(theme_idx, shuffler, cache),
            daemon=True
        )
        self._preload_thread.start()
        logger.debug(f"[ThemeBank] Started background preload thread")
    
    def _preload_initial_lookahead(self, theme_idx: int) -> None:
        """Preload initial 15 EXACT images at startup for instant first frames.
        
        Args:
            theme_idx: Theme index to preload for
        """
        theme = self._themes[theme_idx]
        shuffler = self._shufflers.get(theme_idx)
        cache = self._image_caches.get(theme_idx)
        
        if not shuffler or not cache:
            return
        if self._lookahead_count <= 0 or self._lookahead_batch_size <= 0:
            return
        
        # Get EXACT next indices from shuffler simulation
        initial_limit = min(self._lookahead_count, self._lookahead_batch_size)
        next_indices = shuffler.peek_next(initial_limit)
        
        span = self._perf_span(
            "theme_initial_preload",
            metadata={"theme": theme.name, "theme_idx": theme_idx, "limit": initial_limit},
        )
        preloaded = 0
        with span:
            for idx in next_indices:
                if idx >= len(theme.image_path):
                    continue
                
                path_str = theme.image_path[idx]
                image_path = Path(path_str) if Path(path_str).is_absolute() else self._root_path / path_str
                
                if cache.get_image(image_path) is not None:
                    continue
                
                from .media import load_image_sync

                image_data = load_image_sync(image_path, perf_tracer=self._perf)
                if image_data is not None:
                    while len(cache._cache) >= cache._cache_size:
                        if not cache._lru_order:
                            break
                        oldest_path = cache._lru_order.pop()
                        if oldest_path in cache._cache:
                            del cache._cache[oldest_path]
                    
                    cache._cache[image_path] = type('obj', (object,), {
                        'image_data': image_data,
                        'gpu_texture_id': None
                    })()
                    cache._lru_order.appendleft(image_path)
                    preloaded += 1
            span.annotate(preloaded=preloaded, cache_fill=len(cache._cache))
        
        logger.info(
            f"[ThemeBank] Initial lookahead: preloaded {preloaded} exact images for theme {theme_idx} (cache size: {len(cache._cache)}/{cache._cache_size})"
        )
    
    def get_text_line(self, alternate: bool = False) -> Optional[str]:
        """Get random text line from active theme.
        
        Args:
            alternate: If True, use alternate theme; otherwise primary
        
        Returns:
            Random text line or None
        """
        import random
        
        theme_slot = 2 if alternate else 1
        theme_idx = self._active_theme_indices[theme_slot]
        
        if theme_idx is None:
            return None
        
        theme = self._themes[theme_idx]
        if not theme.text_line:
            return None
        
        return random.choice(theme.text_line)

    def apply_throttle_config(self, config: ThemeBankThrottleConfig) -> None:
        """Update throttle configuration at runtime."""
        self._throttle = config
        self._preload_aggressively = config.preload_aggressively
        self._lookahead_count = max(0, config.lookahead_count)
        self._lookahead_batch_size = max(0, config.lookahead_batch_size)
        self._lookahead_sleep_sec = max(0.0, config.lookahead_sleep_ms) / 1000.0
        self._max_preload_ms = max(0.0, config.max_preload_ms)
        self._sync_warning_ms = max(1.0, config.sync_warning_ms)
        self._background_warning_ms = max(1.0, config.background_warning_ms)
        self._lookahead_counter = 0
        logging.getLogger(__name__).info(
            "[ThemeBank] Applied throttle override: lookahead=%d batch=%d sleep=%.2fms max_ms=%.1f",
            self._lookahead_count,
            self._lookahead_batch_size,
            config.lookahead_sleep_ms,
            self._max_preload_ms,
        )
    
    def async_update(self) -> None:
        """Async update - process background loading.
        
        Should be called regularly (e.g. every frame).
        """
        self._async_update_count += 1
        
        # Process loaded images for all active caches
        for cache in self._image_caches.values():
            cache.process_loaded_images()
        
        # Keep hot cache full - refill every N frames
        # This ensures images are always ready for fast cycling
        if self._async_update_count - self._last_cache_refill >= self._cache_refill_interval:
            self._refill_hot_cache()
            self._last_cache_refill = self._async_update_count
    
    def can_switch_themes(self) -> bool:
        """Check if theme switching is allowed (cooldown expired).
        
        Returns:
            True if can switch themes
        """
        return self._async_update_count - self._last_theme_switch >= self.THEME_SWITCH_COOLDOWN
    
    def switch_themes(self) -> bool:
        """Attempt to switch to next theme set.
        
        Returns:
            True if switched, False if cooldown active
        """
        if not self.can_switch_themes():
            return False
        
        import random
        
        # Select new random themes
        if len(self._themes) >= 2:
            indices = list(range(len(self._themes)))
            random.shuffle(indices)
            self._active_theme_indices[1] = indices[0]
            self._active_theme_indices[2] = indices[1] if len(indices) > 1 else None
        elif len(self._themes) == 1:
            self._active_theme_indices[1] = 0
            self._active_theme_indices[2] = None
        
        self._last_theme_switch = self._async_update_count
        return True
    
    def shutdown(self) -> None:
        """Shutdown all caches."""
        for cache in self._image_caches.values():
            cache.shutdown()
    
    def get_theme_count(self) -> int:
        """Get number of enabled themes."""
        return len(self._themes)
    
    def get_active_theme_names(self) -> tuple[Optional[str], Optional[str]]:
        """Get names of active themes.
        
        Returns:
            (primary_name, alternate_name) tuple
        """
        primary_idx = self._active_theme_indices[1]
        alt_idx = self._active_theme_indices[2]
        
        primary_name = self._themes[primary_idx].name if primary_idx is not None else None
        alt_name = self._themes[alt_idx].name if alt_idx is not None else None
        
        return (primary_name, alt_name)
    
    @property
    def text_lines(self) -> List[str]:
        """Get all text lines from all enabled themes.
        
        Returns:
            Combined list of text lines from all themes
        """
        all_texts = []
        for theme in self._themes:
            if hasattr(theme, 'text_line') and theme.text_line:
                all_texts.extend(theme.text_line)
        return all_texts
    
    def _refill_hot_cache(self) -> None:
        """Legacy hot cache refill - now handled by lookahead preloading.
        
        This method is kept as a no-op for backward compatibility.
        The new lookahead preloading system (triggered in get_image) handles
        cache management more efficiently using the deterministic queue.
        """
        # No-op: Lookahead preloading in get_image() now handles this
        pass

