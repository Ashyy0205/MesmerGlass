# mesmerglass/engine/audio.py
import pygame

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
            print("[audio] pygame mixer initialized")
        except Exception as e:
            print(f"[audio] init failed: {e}")
            return

        self.snd1 = None
        self.snd2 = None
        self.chan1 = None
        self.chan2 = None
        self.music1_path: str | None = None   # streaming fallback

    # -------- loading --------------------------------------------------------
    def load1(self, path: str):
        if not self.init_ok: return
        self.snd1 = None
        self.music1_path = None
        try:
            self.snd1 = pygame.mixer.Sound(path)  # full load
        except Exception as e:
            print(f"[audio] load1 error: {e} — falling back to streaming")
            # streaming fallback (uses global music channel)
            self.music1_path = path

    def load2(self, path: str):
        if not self.init_ok: return
        try:
            self.snd2 = pygame.mixer.Sound(path)
        except Exception as e:
            print(f"[audio] load2 error: {e}")
            self.snd2 = None

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
                print(f"[audio] music play error: {e}")
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
