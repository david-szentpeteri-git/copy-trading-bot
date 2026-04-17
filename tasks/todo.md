# TODO

## Active

- [ ] Test full dry run flow end-to-end (dashboard → start bot → simulated trades appear)
- [ ] Deposit USDC to Polymarket for live trading

## Backlog

- [ ] Investigate whether `bullpen polymarket positions --address <addr>` ever works for external wallets (or find alternative API for trader portfolio estimation)
- [ ] Add log viewer panel to dashboard (tail logs/bot.log)
- [ ] Add auto-refresh without requiring `streamlit-autorefresh` package

## Done

- [x] Fix `'str' object has no attribute 'get'` in portfolio.py — guard non-dict position entries
- [x] Fix `bullpen portfolio balances` JSON parsing — was matching wrong field names
- [x] Fix all trades being skipped — portfolio estimation fails for external wallets, now falls back to raw cap sizing
- [x] Fix dry run mode not executing trades — was still checking real USDC balance
- [x] Add per-trader stats section to dashboard
- [x] Redirect bot logs to `logs/bot.log` when launched from dashboard
