"""Bot process management for the dashboard.

Provides start, stop, and status functions that the Streamlit dashboard
uses to control the main.py daemon. The bot's PID is persisted to
bot.pid so the dashboard can find it across page refreshes.
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

# PID file lives next to the bot scripts
PID_FILE = Path(__file__).parent / "bot.pid"


def start() -> bool:
    """Launch main.py as a background subprocess and save its PID.

    Returns:
        True if the bot started successfully, False if it was already
        running or failed to launch.
    """
    if is_running():
        return False

    log_path = Path(__file__).parent / "logs" / "bot.log"
    log_path.parent.mkdir(exist_ok=True)
    log_file = open(log_path, "a")

    # Launch the bot with the same Python interpreter running the dashboard.
    # Logs go to logs/bot.log so they're readable even when the dashboard is the launcher.
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "main.py")],
        stdout=log_file,
        stderr=log_file,
        # Detach from the current process group so it survives dashboard restarts
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

    PID_FILE.write_text(str(proc.pid))
    return True


def stop() -> bool:
    """Terminate the running bot process.

    Returns:
        True if the process was found and killed, False otherwise.
    """
    pid = _read_pid()
    if pid is None:
        return False

    try:
        if sys.platform == "win32":
            # Windows doesn't support SIGTERM — use taskkill for a clean shutdown
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
            )
        else:
            os.kill(pid, signal.SIGTERM)

        PID_FILE.unlink(missing_ok=True)
        return True

    except (ProcessLookupError, PermissionError):
        # Process already gone — clean up the stale PID file
        PID_FILE.unlink(missing_ok=True)
        return False


def is_running() -> bool:
    """Check whether the bot process is currently alive.

    Returns:
        True if a process with the stored PID is running, False otherwise.
    """
    pid = _read_pid()
    if pid is None:
        return False

    try:
        if sys.platform == "win32":
            # On Windows, check via tasklist — os.kill(pid, 0) isn't reliable
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True,
            )
            alive = str(pid) in result.stdout
        else:
            # Signal 0 checks existence without killing
            os.kill(pid, 0)
            alive = True

    except (ProcessLookupError, PermissionError):
        alive = False

    # Clean up stale PID file if the process is gone
    if not alive:
        PID_FILE.unlink(missing_ok=True)

    return alive


def _read_pid() -> int | None:
    """Read the bot PID from the PID file.

    Returns:
        Integer PID if the file exists and is valid, None otherwise.
    """
    if not PID_FILE.exists():
        return None

    try:
        return int(PID_FILE.read_text().strip())
    except ValueError:
        return None
