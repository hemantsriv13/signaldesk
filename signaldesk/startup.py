"""Optional Windows launcher for the existing, shared Colibri installation."""
from pathlib import Path
import socket
import subprocess
import sys
from urllib.parse import urlsplit

from .config import ModelConfig


def start_local_model(config: ModelConfig, launcher: Path | None = None) -> str:
    """Launch only the known default 4B setup, never replace a listening server.

    Colibri's existing script can stop a running model. Do not invoke it when
    the port is occupied, even if that service is unhealthy or serves another
    model. SignalDesk's normal health checks report readiness afterwards.
    """
    endpoint = urlsplit(config.base_url)
    if (endpoint.scheme != 'http' or endpoint.hostname != '127.0.0.1'
            or endpoint.port != 8000 or endpoint.path.rstrip('/') != '/v1'
            or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
            or config.model_id != ModelConfig().model_id):
        return 'Automatic start skipped: custom model settings. Start your configured model server manually.'
    try:
        with socket.create_connection(('127.0.0.1', 8000), timeout=1):
            return 'Port 8000 is already in use; leaving the existing server untouched.'
    except ConnectionRefusedError:
        pass
    except OSError as exc:
        return f'Automatic start skipped: could not safely check port 8000 ({exc}).'
    if sys.platform != 'win32':
        return 'Automatic Colibri start is supported on Windows. Start the model server manually.'
    launcher = (launcher or Path(__file__).resolve().parents[2] / 'local-ai' / 'start-colibri.cmd').resolve()
    if not launcher.is_file():
        return f'Colibri launcher not found: {launcher}. Start it manually or pass --model-launcher PATH.'
    # PowerShell literal quoting handles spaces and apostrophes without treating
    # the path as executable PowerShell text. Keep Colibri in its own console.
    command = "& '" + str(launcher).replace("'", "''") + "' '4b'"
    try:
        subprocess.Popen(['powershell.exe', '-NoProfile', '-Command', command],
                         cwd=str(launcher.parent), creationflags=subprocess.CREATE_NEW_CONSOLE)
    except OSError as exc:
        return f'Could not start Colibri: {exc}. SignalDesk will still open.'
    return ('Colibri start requested in a separate window. The model may show offline while it loads; '
            'SignalDesk will detect it automatically. If it stays offline, check that window for errors.')
