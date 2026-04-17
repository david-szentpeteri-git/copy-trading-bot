"""Dry run mode manager.

Dry run mode intercepts all real orders and replaces them with simulated
executions using live market prices. All PnL calculations remain realistic
since they use actual Bullpen price data — only the on-chain transactions
are skipped.

State is persisted to a flag file so the setting survives bot restarts.
"""

import json
import os
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


def reset_dry_run_data() -> dict:
    """Clear all dry run history: trade log entries, positions, and seen hashes.

    - Removes all lines from trades.json where dry_run=true.
    - Removes all entries from positions.json where dry_run=true.
    - Clears seen_trades.json entirely so the bot replays recent trades.

    Returns:
        Dict with counts of what was removed, for display in the dashboard.
    """
    from config import config

    removed_trades = 0
    removed_positions = 0

    # ── Strip dry run entries from the trade log ──────────────────────────────
    if os.path.exists(config.trade_log_file):
        kept = []
        with open(config.trade_log_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("dry_run"):
                        removed_trades += 1
                    else:
                        kept.append(line)
                except json.JSONDecodeError:
                    kept.append(line)

        with open(config.trade_log_file, "w") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))

    # ── Strip dry run positions from positions state ───────────────────────────
    if os.path.exists(config.positions_file):
        with open(config.positions_file, "r") as f:
            positions = json.load(f)

        kept_positions = {
            k: v for k, v in positions.items()
            if not v.get("dry_run", False)
        }
        removed_positions = len(positions) - len(kept_positions)

        with open(config.positions_file, "w") as f:
            json.dump(kept_positions, f, indent=2)

    # ── Clear seen trade hashes so the bot replays recent trades ──────────────
    # Handles both a direct file path and a WSL path (\\wsl$\...) transparently
    seen_path = config.seen_trades_file
    wsl_path = f"\\\\wsl$\\Ubuntu{seen_path.replace('/', chr(92))}"

    for path in (seen_path, wsl_path):
        try:
            if os.path.exists(path):
                with open(path, "w") as f:
                    json.dump([], f)
                break
        except (OSError, PermissionError):
            continue

    return {
        "removed_trades": removed_trades,
        "removed_positions": removed_positions,
    }
