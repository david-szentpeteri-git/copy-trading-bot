# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

## Setup

```bash
# Install dependencies (fill in once stack is chosen)
# e.g. pip install -r requirements.txt
```

## Commands

```bash
# Run the bot
# e.g. python main.py

# Run tests
# e.g. pytest

# Lint
# e.g. flake8 . / ruff check .
```

## Architecture

<!-- Fill in as the project grows, e.g.:
- Entry point: main.py
- Trade monitor: watches source account for new positions/orders
- Order executor: places mirror orders on target account
- Config: .env for API keys and account IDs
-->
