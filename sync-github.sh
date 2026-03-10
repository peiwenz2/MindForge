#!/bin/bash
# Sync MindForge to GitHub

WORKSPACE="/home/admin/.openclaw/workspace/mindforge"
REPO_URL="https://github.com/peiwenz2/mindforge.git"

cd "$WORKSPACE"

if git diff --quiet && git diff --cached --quiet; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No changes"
    exit 0
fi

git add -A
git commit -m "Auto-backup: $(date '+%Y-%m-%d %H:%M:%S') - Cycle $(grep 'Cycle' memory/current-state.md 2>/dev/null | head -1)"
git push "$REPO_URL" main 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup complete"
