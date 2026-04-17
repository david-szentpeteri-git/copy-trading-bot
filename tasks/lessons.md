# Lessons Learned

## Bullpen CLI

- `bullpen polymarket positions --address <addr>` only works for your **own** wallet — fails silently for external addresses. Don't use it to estimate trader portfolio values.
- `bullpen portfolio balances --output json` returns `{"chains": [...], "total_usd": ...}` — iterate `chains`, match on `label == "Polymarket"`, read `total_usd`. Not a flat list.
- Auth expires. If all CLI calls fail with empty stderr, run `wsl /home/david/.bullpen/bin/bullpen login`.

## Bot Architecture

- Dry run mode is controlled by a flag file (`dry_run.flag`). Exists = ON, absent = OFF.
- `bot_control.py` manages the bot as a subprocess from the dashboard. Logs go to `logs/bot.log`.
- Trade log is NDJSON at `logs/trades.json`. Positions state is JSON at `logs/positions.json`.

## Dashboard

- Run with: `& 'C:\Users\David\AppData\Local\Programs\Python\Python314\python.exe' -m streamlit run dashboard.py`
- `streamlit` is not on PATH — always invoke via `python -m streamlit`.
- `missing ScriptRunContext` warnings are harmless; they appear at module import time.

## Trade Sizing

- When trader portfolio is unknown, fall back to mirroring raw trade amount capped at `trade_cap_usdc`.
- In dry run mode, use a simulated $1000 own balance so trades execute without real USDC.
