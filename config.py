"""Configuration loader for the Polymarket copy trading bot.

Reads settings from environment variables (via .env) and exposes
them as typed constants used throughout the application.
"""

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Central configuration for the copy trading bot.

    Attributes:
        traders: List of Polymarket proxy wallet addresses to monitor.
        trade_cap_usdc: Maximum USDC to spend on any single copied trade.
        poll_interval_seconds: How often (in seconds) to poll for new trades.
        bullpen_bin: Path to the bullpen CLI binary inside WSL.
        seen_trades_file: Path to persist already-copied trade hashes.
        positions_file: Path to persist our active position state.
        trade_log_file: Path to the append-only JSON trade log for the dashboard.
    """

    traders: List[str] = field(default_factory=lambda: [
        # rank1_anon — $7.06M PnL this week
        "0x492442eab586f242b53bda933fd5de859c8a3782",
        # beachboy4 — $2.67M PnL this week
        "0xc2e7800b5af46e6093872b177b7a5e7f0563be51",
        # Countryside — $2.29M PnL this week
        "0xbddf61af533ff524d27154e589d2d7a81510c684",
        # rank6_anon — $2.15M PnL this week
        "0x2a2c53bd278c04da9962fcf96490e17f3dfb9bc1",
        # RN1 — $2.12M PnL this week
        "0x2005d16a84ceefa912d4e380cd32e7ff827875ea",
    ])

    # Hard cap per trade in USDC — never bet more than this on a single copy
    trade_cap_usdc: float = float(os.getenv("TRADE_CAP_USDC", "10.0"))

    # Seconds between polling cycles
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

    # Full path to bullpen binary (inside the WSL environment)
    bullpen_bin: str = os.getenv("BULLPEN_BIN", "/home/david/.bullpen/bin/bullpen")

    # File to store already-processed transaction hashes (prevents double-copying)
    seen_trades_file: str = os.getenv("SEEN_TRADES_FILE", "/home/david/.bullpen/seen_trades.json")

    # File to persist active position state (our tokens held per market/outcome)
    positions_file: str = os.getenv("POSITIONS_FILE", "logs/positions.json")

    # Append-only JSON log of every trade event — consumed by the future dashboard
    trade_log_file: str = os.getenv("TRADE_LOG_FILE", "logs/trades.json")


# Module-level singleton — import this everywhere
config = Config()
