#!/usr/bin/env bash
# memory.sh — Launch Claude with full project context as the system prompt.

PRIMER=""
if [ -f "/root/.claude/primer.md" ]; then
  PRIMER=$(cat /root/.claude/primer.md)
fi

COMMITS=$(git log --oneline -5 2>/dev/null || echo "(no git history)")

MODIFIED=$(git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)
if [ -z "$MODIFIED" ]; then
  MODIFIED="(none)"
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

LESSONS=""
if [ -f "tasks/lessons.md" ]; then
  LESSONS=$(cat tasks/lessons.md)
fi

SYSTEM_PROMPT="$(cat <<EOF
${PRIMER}

## Project: Polymarket Copy Trading Bot

### Current Branch
${BRANCH}

### Last 5 Commits
${COMMITS}

### Modified / Untracked Files
${MODIFIED}

### Lessons Learned
${LESSONS}
EOF
)"

claude \
  --permission-mode acceptEdits \
  --allowedTools "Bash(git:*) Bash(npm:*) Edit Write Read" \
  --system-prompt "${SYSTEM_PROMPT}" \
  "$@"
