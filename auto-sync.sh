#!/bin/bash
# MindForge Auto-Sync Cron Job
# Runs every 3 minutes to sync research progress to GitHub
# Uses git credential helper for authentication

WORKSPACE="/home/admin/.openclaw/workspace/mindforge-repo"
REPO_URL="https://github.com/peiwenz2/MindForge.git"
LOG_FILE="/home/admin/.openclaw/workspace/mindforge-repo/logs/sync.log"

cd "$WORKSPACE"

# Configure git user
git config user.email "peiwenz2@users.noreply.github.com"
git config user.name "peiwenz2"

# Check for changes
if git diff --quiet && git diff --cached --quiet; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No changes to sync" >> "$LOG_FILE"
    exit 0
fi

# Add, commit, and push
git add -A
git commit -m "Auto-sync: $(date '+%Y-%m-%d %H:%M:%S')"
git push "$REPO_URL" master 2>&1 | tee -a "$LOG_FILE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sync complete" >> "$LOG_FILE"
