"""No-duplicate-positions mode manager.

When enabled, the bot skips any BUY for a market outcome we already hold
a position in, regardless of whether the tracked trader is buying again.
Toggle via the dashboard or by creating/removing the flag file manually.

State is persisted to a flag file so the setting survives bot restarts.
"""

from pathlib import Path

_FLAG_FILE = Path(__file__).parent / "no_duplicates.flag"


def is_enabled() -> bool:
    """Return True if duplicate-position prevention is active.

    Returns:
        True if the no_duplicates.flag file exists, False otherwise.
    """
    return _FLAG_FILE.exists()


def enable() -> None:
    """Activate no-duplicate mode by creating the flag file."""
    _FLAG_FILE.touch()


def disable() -> None:
    """Deactivate no-duplicate mode by removing the flag file."""
    _FLAG_FILE.unlink(missing_ok=True)


def toggle() -> bool:
    """Toggle no-duplicate mode and return the new state.

    Returns:
        True if now ON, False if now OFF.
    """
    if is_enabled():
        disable()
        return False
    else:
        enable()
        return True
