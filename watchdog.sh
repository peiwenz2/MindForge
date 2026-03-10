#!/bin/bash
# MindForge Watchdog - Auto-restart if crashed

WORKSPACE="/home/admin/.openclaw/workspace/mindforge"
LOG_FILE="$WORKSPACE/logs/watchdog.log"
MAX_RESTARTS_PER_HOUR=10
RESTART_COUNT_FILE="$WORKSPACE/logs/restart-count.txt"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

get_restart_count() {
    cat "$RESTART_COUNT_FILE" 2>/dev/null || echo "0"
}

increment_restart_count() {
    local count=$(get_restart_count)
    echo $((count + 1)) > "$RESTART_COUNT_FILE"
}

reset_restart_count() {
    echo "0" > "$RESTART_COUNT_FILE"
}

start_mindforge() {
    log "🚀 Starting MindForge..."
    cd "$WORKSPACE"
    pkill -f "convergence.py" 2>/dev/null
    sleep 2
    nohup python3 convergence.py > logs/mindforge.log 2>&1 &
    local pid=$!
    sleep 3
    if ps -p $pid > /dev/null 2>&1; then
        log "✅ MindForge started (PID: $pid)"
        return 0
    else
        log "❌ Failed to start"
        return 1
    fi
}

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "🔍 MindForge Watchdog started"
log "📊 Check interval: 30 seconds"
log "⚠️  Max restarts/hour: $MAX_RESTARTS_PER_HOUR"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

reset_restart_count
start_mindforge

while true; do
    if ! pgrep -f "convergence.py" > /dev/null; then
        log "❌ MindForge NOT running!"
        count=$(get_restart_count)
        if [ "$count" -lt "$MAX_RESTARTS_PER_HOUR" ]; then
            increment_restart_count
            log "🔄 Restart attempt #$((count+1))"
            start_mindforge
        else
            log "⚠️  Restart limit reached. Manual intervention needed."
        fi
    else
        pid=$(pgrep -f "convergence.py" | head -1)
        log "✅ MindForge alive (PID: $pid)"
    fi
    sleep 30
done
