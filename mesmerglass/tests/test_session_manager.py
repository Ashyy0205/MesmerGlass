"""Test SessionManager functionality."""

import logging
from pathlib import Path
from mesmerglass.session_manager import SessionManager

logging.basicConfig(level=logging.INFO)

def test_session_manager():
    """Test SessionManager basic operations."""
    print("=== Testing SessionManager ===\n")
    
    # Create manager
    sm = SessionManager()
    print(f"✓ SessionManager created: {sm.session_dir}\n")
    
    # Test listing sessions
    sessions = sm.list_sessions()
    print(f"✓ Found {len(sessions)} existing sessions:")
    for s in sessions:
        print(f"  - {s.name}")
    print()
    
    # Test loading example session
    if sessions:
        print(f"Loading: {sessions[0].name}")
        session = sm.load_session(sessions[0])
        print(f"✓ Loaded session: {session['metadata']['name']}")
        print(f"  - Playbacks: {len(session['playbacks'])}")
        print(f"  - Cuelists: {len(session['cuelists'])}")
        print(f"  - Display output: {session['display']['output']}")
        print()
    
    # Test creating new session
    print("Creating new session...")
    new_session = sm.new_session("Test Session", "Testing session creation")
    print(f"✓ Created session: {new_session['metadata']['name']}")
    print(f"  - Version: {new_session['version']}")
    print(f"  - Created: {new_session['metadata']['created']}")
    print()
    
    # Test adding playback
    print("Adding playback...")
    playback = sm.create_default_playback("Test Playback", "standard")
    sm.add_playback("test_pb", playback)
    print(f"✓ Added playback: test_pb")
    print(f"  - Spiral type: {playback['spiral']['type']}")
    print(f"  - Rotation speed: {playback['spiral']['rotation_speed']}")
    print()
    
    # Test adding cuelist
    print("Adding cuelist...")
    cuelist = sm.create_default_cuelist("Test Cuelist", "once")
    cuelist["cues"].append({
        "name": "Test Cue",
        "duration": 60,
        "playback_pool": ["test_pb"],
        "audio": {"tracks": [], "volume": 1.0}
    })
    sm.add_cuelist("test_cl", cuelist)
    print(f"✓ Added cuelist: test_cl")
    print(f"  - Loop mode: {cuelist['loop_mode']}")
    print(f"  - Cues: {len(cuelist['cues'])}")
    print()
    
    # Test dirty state
    print(f"✓ Session is dirty: {sm.dirty}")
    print()
    
    # Test save
    save_path = sm.session_dir / "test_session.session.json"
    print(f"Saving to: {save_path.name}")
    sm.save_session(save_path)
    print(f"✓ Saved session")
    print(f"  - Dirty state: {sm.dirty}")
    print()
    
    # Test reload
    print(f"Reloading: {save_path.name}")
    reloaded = sm.load_session(save_path)
    print(f"✓ Reloaded session: {reloaded['metadata']['name']}")
    print(f"  - Playbacks: {list(reloaded['playbacks'].keys())}")
    print(f"  - Cuelists: {list(reloaded['cuelists'].keys())}")
    print()
    
    print("=== All Tests Passed! ===")

if __name__ == "__main__":
    test_session_manager()
