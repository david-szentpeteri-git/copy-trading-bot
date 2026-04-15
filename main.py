"""Entry point for the Polymarket copy trading bot.

Runs a continuous polling daemon that monitors 5 top Polymarket traders,
detects new BUY and SELL trades, and automatically replicates them
proportionally on our own account — capped at $10 per copied BUY.

All trade outcomes are appended to logs/trades.json for dashboard use.

Usage:
    python main.py
"""

import logging
import time
from datetime import datetime, timezone

from config import config
from executor import handle_trade
from monitor import get_since_timestamp, load_seen_trades, poll_new_trades, save_seen_trades
import state

# Configure structured logging to stdout with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run() -> None:
    """Start the copy trading daemon loop.

    On startup:
    - Loads persisted position state (or recovers from Bullpen if missing)
    - Loads seen trade hashes to prevent duplicate execution on restart
    - Begins polling all tracked traders every poll_interval_seconds

    Each cycle:
    - Fetches new trades (BUY and SELL) from all 5 tracked wallets
    - Routes each to execute_buy or execute_sell in executor.py
    - Logs every outcome to logs/trades.json
    - Persists seen hashes and position state to disk
    """
    logger.info("Copy trading bot starting up")
    logger.info("Tracking %d traders: %s", len(config.traders), config.traders)
    logger.info("Trade cap: $%.2f USDC | Poll interval: %ds", config.trade_cap_usdc, config.poll_interval_seconds)

    # Load position state first — needed by executor to handle SELL trades
    state.load()

    # Load seen hashes to avoid re-executing trades after a restart
    seen_hashes = load_seen_trades()
    logger.info("Loaded %d previously seen trade hashes", len(seen_hashes))

    # Only look back 1 hour on first run to avoid copying stale trades
    since = get_since_timestamp()
    logger.info("Starting trade lookback from: %s", since)

    while True:
        logger.info("--- Polling cycle started ---")

        new_count = 0
        success_count = 0

        for trade in poll_new_trades(since, seen_hashes):
            new_count += 1
            tx_hash = trade["transaction_hash"]

            try:
                success = handle_trade(trade)
            except Exception as exc:
                # Catch any unexpected errors so a single bad trade never kills the loop
                logger.error("Unhandled error processing tx %s: %s", tx_hash, exc)
                success = False

            # Mark as seen regardless of outcome to prevent retry loops on errors
            seen_hashes.add(tx_hash)

            if success:
                success_count += 1

        if new_count > 0:
            logger.info(
                "Cycle complete: %d new trades processed, %d executed successfully",
                new_count, success_count,
            )
            save_seen_trades(seen_hashes)
        else:
            logger.info("No new trades found")

        # Advance the lookback window to now so the next cycle is incremental
        since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    run()
