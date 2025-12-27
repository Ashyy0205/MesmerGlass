"""Session management for MesmerGlass Phase 7.

This module handles creation, loading, saving, and validation of session files.
Sessions consolidate all playbacks, cuelists, cues, and settings into a single
.session.json file.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from .platform_paths import ensure_dir, get_sessions_dir

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages session save/load operations and state tracking.
    
    A session contains:
    - metadata (name, description, created/modified timestamps)
    - display settings (monitor, VR, fullscreen)
    - playbacks (spiral, media, text, zoom configurations)
    - cuelists (timed sequences of playbacks)
    - runtime state (active cuelist, current cue, elapsed time)
    """
    
    def __init__(self, session_dir: Optional[Path] = None):
        """Initialize SessionManager.
        
        Args:
            session_dir: Directory for session files. Defaults to a persistent per-user
                folder (e.g. %APPDATA%\\MesmerGlass\\sessions on Windows).
        """
        if session_dir is None:
            session_dir = get_sessions_dir()
        
        self.session_dir = Path(session_dir)
        ensure_dir(self.session_dir)

        # Copy bundled demo sessions into the user sessions directory if missing.
        # This keeps the editor usable out-of-the-box while ensuring user sessions
        # never live inside temp/installer locations.
        self._seed_sessions_from_bundled()
        
        self.current_session: Optional[Dict[str, Any]] = None
        self.current_file: Optional[Path] = None
        self.dirty: bool = False
        
        logger.info(f"SessionManager initialized: {self.session_dir}")

    def _seed_sessions_from_bundled(self) -> None:
        bundled_dir = Path(__file__).parent / "sessions"
        if not bundled_dir.exists():
            return
        if bundled_dir.resolve() == self.session_dir.resolve():
            return

        copied = 0
        try:
            for src in bundled_dir.glob("*.session.json"):
                dst = self.session_dir / src.name
                if dst.exists():
                    continue
                try:
                    dst.write_bytes(src.read_bytes())
                    copied += 1
                except Exception as exc:
                    logger.warning("Failed copying bundled session %s: %s", src.name, exc)
        except Exception as exc:
            logger.warning("Bundled session seeding failed: %s", exc)
        if copied:
            logger.info("Seeded %s bundled session(s) into %s", copied, self.session_dir)
    
    def new_session(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new empty session.
        
        Args:
            name: Human-readable session name
            description: Optional session description
        
        Returns:
            New session dictionary with default structure
        """
        now = datetime.now().isoformat()
        
        session = {
            "version": "1.0",
            "metadata": {
                "name": name,
                "description": description,
                "created": now,
                "modified": now,
                "author": "",
                "tags": []
            },
            "playbacks": {},
            "cuelists": {},
            "runtime": {
                "active_cuelist": None,
                "active_cue_index": 0,
                "last_playback": None,
                "session_time_elapsed": 0
            },
            "media_bank": []
        }
        
        self.current_session = session
        self.current_file = None
        self.dirty = True
        
        logger.info(f"Created new session: {name}")
        return session
    
    def load_session(self, filepath: Path) -> Dict[str, Any]:
        """Load session from file.
        
        Args:
            filepath: Path to .session.json file
        
        Returns:
            Loaded session dictionary
        
        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is invalid JSON
            ValueError: If session structure is invalid
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            raise FileNotFoundError(f"Session file not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            session = json.load(f)
        
        # Validate session structure
        self._validate_session(session)
        
        if "media_bank" not in session:
            session["media_bank"] = []
        
        self.current_session = session
        self.current_file = filepath
        self.dirty = False
        
        name = session["metadata"]["name"]
        logger.info(f"Loaded session: {name} from {filepath.name}")
        return session
    
    def save_session(self, filepath: Optional[Path] = None, session_data: Optional[Dict[str, Any]] = None) -> Path:
        """Save session to file.
        
        Args:
            filepath: Path to save to. If None, uses current_file.
            session_data: Session data to save. If None, uses current_session.
        
        Returns:
            Path where session was saved
        
        Raises:
            ValueError: If no filepath provided and no current_file set
        """
        if filepath is None:
            if self.current_file is None:
                raise ValueError("No filepath provided and no current file set")
            filepath = self.current_file
        
        if session_data is None:
            if self.current_session is None:
                raise ValueError("No session data to save")
            session_data = self.current_session
        
        filepath = Path(filepath)
        
        # Ensure .session.json extension
        if not filepath.name.endswith('.session.json'):
            filepath = filepath.with_suffix('.session.json')
        
        # Update modified timestamp
        session_data["metadata"]["modified"] = datetime.now().isoformat()
        
        # Save with pretty formatting
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        self.current_file = filepath
        self.current_session = session_data
        self.dirty = False
        
        name = session_data["metadata"]["name"]
        logger.info(f"Saved session: {name} to {filepath.name}")
        return filepath
    
    def mark_dirty(self):
        """Mark current session as having unsaved changes."""
        if not self.dirty:
            self.dirty = True
            logger.debug("Session marked as dirty (unsaved changes)")
    
    def mark_clean(self):
        """Mark current session as saved (no unsaved changes)."""
        if self.dirty:
            self.dirty = False
            logger.debug("Session marked as clean (saved)")
    
    def get_session_name(self) -> Optional[str]:
        """Get current session name.
        
        Returns:
            Session name or None if no session loaded
        """
        if self.current_session is None:
            return None
        return self.current_session["metadata"]["name"]
    
    def get_session_filepath(self) -> Optional[Path]:
        """Get current session file path.
        
        Returns:
            Path to current session file or None if not saved yet
        """
        return self.current_file
    
    def list_sessions(self) -> list[Path]:
        """List all session files in session directory.
        
        Returns:
            List of paths to .session.json files
        """
        return sorted(self.session_dir.glob("*.session.json"))
    
    def _validate_session(self, session: Dict[str, Any]):
        """Validate session structure.
        
        Args:
            session: Session dictionary to validate
        
        Raises:
            ValueError: If session structure is invalid
        """
        # Check required top-level keys
        required_keys = ["version", "metadata", "playbacks", "cuelists", "runtime"]
        for key in required_keys:
            if key not in session:
                raise ValueError(f"Session missing required key: {key}")
        
        # Check metadata
        required_metadata = ["name", "created", "modified"]
        for key in required_metadata:
            if key not in session["metadata"]:
                raise ValueError(f"Session metadata missing required key: {key}")
        
        # Check playbacks
        if not isinstance(session["playbacks"], dict):
            raise ValueError("Session playbacks must be a dictionary")
        
        # Check cuelists
        if not isinstance(session["cuelists"], dict):
            raise ValueError("Session cuelists must be a dictionary")
        
        # Check runtime
        if not isinstance(session["runtime"], dict):
            raise ValueError("Session runtime must be a dictionary")

        # Media bank is optional for backward compatibility but must be a list if present
        if "media_bank" in session:
            if not isinstance(session["media_bank"], list):
                raise ValueError("Session media_bank must be a list")
        else:
            session["media_bank"] = []
        
        logger.debug(f"Session validation passed: {session['metadata']['name']}")

    # Media banks are session-specific; no default loading from media_bank.json anymore.
    
    def create_default_playback(self, name: str, playback_type: str = "standard") -> Dict[str, Any]:
        """Create a default playback configuration.
        
        Args:
            name: Playback name
            playback_type: Type of playback (standard, intense, gentle, minimal)
        
        Returns:
            Default playback dictionary
        """
        configs = {
            "standard": {
                "spiral": {"type": "logarithmic", "rotation_speed": 40.0, "opacity": 0.48, "reverse": True},
                "zoom": {"mode": "exponential", "rate": 20.0}
            },
            "intense": {
                "spiral": {"type": "logarithmic", "rotation_speed": 100.0, "opacity": 0.65, "reverse": True},
                "zoom": {"mode": "exponential", "rate": 30.0}
            },
            "gentle": {
                "spiral": {"type": "sqrt", "rotation_speed": 20.0, "opacity": 0.35, "reverse": False},
                "zoom": {"mode": "exponential", "rate": 10.0}
            },
            "minimal": {
                "spiral": {"type": "linear", "rotation_speed": 10.0, "opacity": 0.2, "reverse": False},
                "zoom": {"mode": "none", "rate": 0.0}
            }
        }
        
        config = configs.get(playback_type, configs["standard"])
        
        return {
            "name": name,
            "spiral": config["spiral"],
            "media": {
                "mode": "images",
                "cycle_speed": 50,
                "fade_duration": 0.5,
                "use_theme_bank": False,
                "paths": [],
                "bank_selections": [0]
            },
            "text": {
                "enabled": True,
                "mode": "centered_sync",
                "opacity": 0.69,
                "use_theme_bank": True,
                "library": [],
                "sync_with_media": False,
                "manual_cycle_speed": 50,
                "color": [1.0, 1.0, 1.0]
            },
            "zoom": config["zoom"]
        }
    
    def create_default_cuelist(self, name: str, loop_mode: str = "once") -> Dict[str, Any]:
        """Create a default cuelist configuration.
        
        Args:
            name: Cuelist name
            loop_mode: Loop mode (once, loop, loop_count)
        
        Returns:
            Default cuelist dictionary
        """
        return {
            "name": name,
            "loop_mode": loop_mode,
            "cues": []
        }
    
    def add_playback(self, key: str, playback_data: Dict[str, Any]):
        """Add playback to current session.
        
        Args:
            key: Unique playback identifier
            playback_data: Playback configuration dictionary
        
        Raises:
            ValueError: If no session is loaded
        """
        if self.current_session is None:
            raise ValueError("No session loaded")
        
        self.current_session["playbacks"][key] = playback_data
        self.mark_dirty()
        logger.info(f"Added playback: {key}")
    
    def remove_playback(self, key: str):
        """Remove playback from current session.
        
        Args:
            key: Playback identifier to remove
        
        Raises:
            ValueError: If no session is loaded
            KeyError: If playback doesn't exist
        """
        if self.current_session is None:
            raise ValueError("No session loaded")
        
        del self.current_session["playbacks"][key]
        self.mark_dirty()
        logger.info(f"Removed playback: {key}")
    
    def add_cuelist(self, key: str, cuelist_data: Dict[str, Any]):
        """Add cuelist to current session.
        
        Args:
            key: Unique cuelist identifier
            cuelist_data: Cuelist configuration dictionary
        
        Raises:
            ValueError: If no session is loaded
        """
        if self.current_session is None:
            raise ValueError("No session loaded")
        
        self.current_session["cuelists"][key] = cuelist_data
        self.mark_dirty()
        logger.info(f"Added cuelist: {key}")
    
    def remove_cuelist(self, key: str):
        """Remove cuelist from current session.
        
        Args:
            key: Cuelist identifier to remove
        
        Raises:
            ValueError: If no session is loaded
            KeyError: If cuelist doesn't exist
        """
        if self.current_session is None:
            raise ValueError("No session loaded")
        
        del self.current_session["cuelists"][key]
        self.mark_dirty()
        logger.info(f"Removed cuelist: {key}")
