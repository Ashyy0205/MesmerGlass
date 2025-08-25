# mesmerglass/engine/audio.py
import pygame
import logging
import os

def clamp(x, a, b): return max(a, min(b, x))

class Audio2:
    """
    - Audio 1: tries Sound; on failure falls back to streamed music (pygame.mixer.music)
    - Audio 2: Sound only (for layering a small loop over the streamed track)
    """
    def __init__(self):
        self.init_ok = False
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            self.init_ok = True
            logging.getLogger(__name__).info("pygame mixer initialized")
        except Exception as e:
            logging.getLogger(__name__).error("audio init failed: %s", e)
            return
        # Initialize state after successful (or failed) init attempt so callers
        # can still inspect attributes even if init_ok is False.
        self.snd1 = None
        self.snd2 = None
        self.chan1 = None
        self.chan2 = None
        self.music1_path: str | None = None   # streaming fallback
        self.snd1_path: str | None = None
        self.snd2_path: str | None = None

    # -------- loading --------------------------------------------------------
    def load1(self, path: str):
        if not self.init_ok: return
        self.snd1 = None
        self.snd1_path = None
        self.music1_path = None
        try:
            self.snd1 = pygame.mixer.Sound(path)  # full load
            self.snd1_path = path
        except Exception as e:
            logging.getLogger(__name__).warning("load1 error: %s — falling back to streaming", e)
            # streaming fallback (uses global music channel)
            self.music1_path = path

    def load2(self, path: str):
        if not self.init_ok: return
        try:
            self.snd2 = pygame.mixer.Sound(path)
            self.snd2_path = path
        except Exception as e:
            logging.getLogger(__name__).error("load2 error: %s", e)
            self.snd2 = None
            self.snd2_path = None

    # -------- playback -------------------------------------------------------
    def play(self, vol1=0.5, vol2=0.5):
        if not self.init_ok: return

        # Audio 1
        if self.music1_path:
            try:
                pygame.mixer.music.load(self.music1_path)
                pygame.mixer.music.set_volume(clamp(vol1, 0, 1))
                pygame.mixer.music.play(loops=-1)
            except Exception as e:
                logging.getLogger(__name__).error("music play error: %s", e)
        elif self.snd1 and not self.chan1:
            self.chan1 = self.snd1.play(loops=-1)
            if self.chan1:
                self.chan1.set_volume(clamp(vol1, 0, 1))

        # Audio 2
        if self.snd2 and not self.chan2:
            self.chan2 = self.snd2.play(loops=-1)
            if self.chan2:
                self.chan2.set_volume(clamp(vol2, 0, 1))

    def stop(self):
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass
        if self.chan1:
            self.chan1.stop(); self.chan1 = None
        if self.chan2:
            self.chan2.stop(); self.chan2 = None

    def set_vols(self, v1, v2):
        v1 = clamp(v1, 0, 1); v2 = clamp(v2, 0, 1)
        if self.music1_path:
            # streamed track
            try:
                pygame.mixer.music.set_volume(v1)
            except Exception:
                pass
        elif self.chan1:
            self.chan1.set_volume(v1)
        if self.chan2:
            self.chan2.set_volume(v2)

    # -------- performance helpers -----------------------------------------
    def memory_usage_bytes(self) -> dict:
        """Approximate memory footprint of loaded audio assets.

        For fully loaded sounds we use file size as a proxy (decoded size may be
        larger, but this keeps implementation lightweight). For streaming track
        we return None bytes and flag streaming True.
        """
        def _size(p: str | None):
            if not p: return None
            try: return os.path.getsize(p)
            except Exception: return None
        return {
            "audio1_bytes": _size(self.snd1_path),
            "audio2_bytes": _size(self.snd2_path),
            "audio1_streaming": bool(self.music1_path is not None),
        }
