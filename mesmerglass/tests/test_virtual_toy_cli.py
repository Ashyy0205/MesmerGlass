import asyncio
import subprocess
import sys
import time
import json
import os
import pytest

from mesmerglass.engine.buttplug_server import ButtplugServer

@pytest.mark.asyncio
async def test_cli_toy_smoke(tmp_path):
    # Start server on an ephemeral port
    server = ButtplugServer(port=0)
    server.start()
    await asyncio.sleep(0.2)
    port = server.selected_port

    # Run CLI toy for a short duration
    env = os.environ.copy()
    # Use plain logs for stability
    cmd = [sys.executable, "-m", "mesmerglass", "toy", "--port", str(port), "--run-for", "0.6"]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=10)

    # Ensure clean exit
    assert proc.returncode == 0, proc.stderr

    # Device should be registered
    await asyncio.sleep(0.2)
    dl = server.get_device_list()
    assert len(dl.devices) == 1

    server.stop()
    await asyncio.sleep(0.2)
