"""Entry point for the Polymarket copy trading bot.

Runs a continuous polling daemon that monitors 5 top Polymarket traders,
detects new BUY trades, and automatically replicates them proportionally
on our own account — capped at $10 per trade.

Usage:
    python main.py
"""

import logging
import time

from config import config
from executor import execute_copy_trade
from monitor import get_since_timestamp, load_seen_trades, poll_new_trades, save_seen_trades

# Configure structured logging to stdout with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run() -> None:
    """Start the copy trading daemon loop.

    Polls tracked traders every `config.poll_interval_seconds` seconds.
    On each cycle, any new BUY trades are sized and executed. The set
    of processed transaction hashes is persisted to disk so restarts
    do not cause duplicate trades.
    """
    logger.info("Copy trading bot starting up")
    logger.info("Tracking %d traders: %s", len(config.traders), config.traders)
    logger.info("Trade cap: $%.2f USDC | Poll interval: %ds", config.trade_cap_usdc, config.poll_interval_seconds)

    # Load persisted trade history to avoid re-copying on restart
    seen_hashes = load_seen_trades()
    logger.info("Loaded %d previously seen trade hashes", len(seen_hashes))

    # On first run, only look back 1 hour to avoid copying old trades
    since = get_since_timestamp()
    logger.info("Starting trade lookback from: %s", since)

    while True:
        logger.info("--- Polling cycle started ---")

        new_trade_count = 0
        copied_count = 0

        for trade in poll_new_trades(since, seen_hashes):
            new_trade_count += 1
            tx_hash = trade["transaction_hash"]

            success = execute_copy_trade(trade)

            # Mark as seen regardless of outcome to prevent retry loops
            seen_hashes.add(tx_hash)

            if success:
                copied_count += 1

        if new_trade_count > 0:
            logger.info(
                "Cycle complete: %d new trades found, %d copied successfully",
                new_trade_count, copied_count,
            )
            # Persist updated seen hashes after each cycle with new trades
            save_seen_trades(seen_hashes)
        else:
            logger.info("No new trades found")

        # Move the lookback window forward to now so next cycle is incremental
        from datetime import datetime, timezone
        since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    run()
