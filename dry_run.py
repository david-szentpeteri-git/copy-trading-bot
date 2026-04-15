"""Dry run mode manager.

Dry run mode intercepts all real orders and replaces them with simulated
executions using live market prices. All PnL calculations remain realistic
since they use actual Bullpen price data — only the on-chain transactions
are skipped.

State is persisted to a flag file so the setting survives bot restarts.
"""

from pathlib import Path

# Flag file: exists = dry run ON, absent = dry run OFF
_FLAG_FILE = Path(__file__).parent / "dry_run.flag"


def is_enabled() -> bool:
    """Return True if dry run mode is currently active.

    Returns:
        True if the dry_run.flag file exists, False otherwise.
    """
    return _FLAG_FILE.exists()


def enable() -> None:
    """Activate dry run mode by creating the flag file."""
    _FLAG_FILE.touch()


def disable() -> None:
    """Deactivate dry run mode by removing the flag file."""
    _FLAG_FILE.unlink(missing_ok=True)


def toggle() -> bool:
    """Toggle dry run mode and return the new state.

    Returns:
        True if dry run is now ON, False if now OFF.
    """
    if is_enabled():
        disable()
        return False
    else:
        enable()
        return True
