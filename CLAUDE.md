# CLAUDE.md

@/root/.claude/primer.md
@.claude-memory.md

## PROJECT CONTEXT

**Project:** Polymarket Copy Trading Bot
A bot that monitors tracked trader wallets on Polymarket and automatically mirrors their trades proportionally on your own account.

## PROJECT RULES

- Read `tasks/lessons.md` at the start of every session for hard-won context.
- Update `tasks/todo.md` as you complete or discover work items.

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Behavior Guidelines

- **Act autonomously** — do not ask for permission before taking actions. Execute tasks directly.
- **Clarify before building** — always use `AskUserQuestion` to reach full clarity on requirements before proceeding with implementation. Keep asking until there is no ambiguity.

## Project Overview

A copy trading bot that monitors one or more source trader accounts and automatically replicates their trades on a connected brokerage/exchange account in real time.

## Git Workflow

**Commit frequently** — after every meaningful unit of work (new feature, bug fix, refactor, config change). Do not batch unrelated changes into one commit.

```bash
# Stage and commit
git add <specific files>
git commit -m "short description of what changed"

# Push to remote
git push origin main
```

Commit message format: `<type>: <short description>` — e.g. `feat: add order mirroring logic`, `fix: handle partial fills`, `chore: update deps`.

## Commenting Conventions

All Python code in this repo **must** follow these conventions:

- **Every function and class** gets a Google-style docstring:
  ```python
  def my_function(param: str) -> int:
      """Short one-line summary.

      Longer explanation if needed.

      Args:
          param: What this parameter does.

      Returns:
          What the function returns.

      Raises:
          ValueError: When and why this is raised.
      """
  ```
- **Inline comments** on any non-obvious logic — placed above the line, not at end of line:
  ```python
  # Polymarket uses proxy wallets, not EOA addresses directly
  address = get_proxy_wallet(eoa)
  ```
- **Module-level docstring** at the top of every file explaining its purpose.
- Do **not** add comments that just restate what the code does — only explain *why*.

## Setup

```bash
pip install -r requirements.txt
```

## Commands

```bash
# Run the bot
python main.py

# Run tests
pytest

# Lint
ruff check .
```

## Architecture

- **Entry point**: `main.py` — starts the daemon loop
- **`monitor.py`** — polls tracked trader activity via Bullpen CLI, detects new trades
- **`executor.py`** — sizes and places copy trades via Bullpen CLI
- **`portfolio.py`** — fetches portfolio value for tracked traders and own account
- **`config.py`** — loads settings from `.env` (trader addresses, cap, scale logic)

### Copy Sizing Logic
For each detected trade:
1. Fetch the trader's total portfolio value (open positions + USDC balance)
2. Calculate what % of their portfolio they used: `trade_usdc / trader_portfolio`
3. Apply the same % to your own portfolio: `your_portfolio * pct`
4. Cap at **$10** — never place more than $10 on a single copied trade
5. Execute via `bullpen polymarket buy`
