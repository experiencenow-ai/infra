#!/bin/bash
# Experience v2 - run.sh

set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[v2]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; }

check_env() {
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        [ -f .env ] && export $(grep -v '^#' .env | xargs)
    fi
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        err "ANTHROPIC_API_KEY not set"
        exit 1
    fi
}

case "${1:-help}" in
    wake)
        check_env
        CITIZEN="${2:-opus}"
        log "Wake $CITIZEN"
        python3 core.py --citizen "$CITIZEN" --wake
        ;;
    loop)
        check_env
        CITIZEN="${2:-opus}"
        log "Loop $CITIZEN (Ctrl+C to stop)"
        python3 core.py --citizen "$CITIZEN" --loop
        ;;
    status)
        CITIZEN="${2:-opus}"
        log "Status $CITIZEN"
        python3 core.py --citizen "$CITIZEN" --status
        ;;
    talk|prompt)
        check_env
        CITIZEN="${2:-opus}"
        MSG="$3"
        if [ -z "$MSG" ]; then
            # No initial message - just start interactive
            log "Interactive mode with $CITIZEN"
            python3 core.py --citizen "$CITIZEN" --interactive
        else
            log "Talking to $CITIZEN"
            python3 core.py --citizen "$CITIZEN" --interactive --message "$MSG"
        fi
        ;;
    restore)
        CITIZEN="${2:-opus}"
        LOGS="${3:-/root/claude/$CITIZEN/logs}"
        log "Restore $CITIZEN from $LOGS"
        python3 scripts/restore_citizens.py "$CITIZEN" "$LOGS"
        ;;
    push)
        log "Push to GitHub"
        ./scripts/PUSH_TO_GITHUB.sh
        ;;
    sync)
        log "Syncing all citizens from GitHub"
        ./scripts/sync_all.sh
        ;;
    logs)
        CITIZEN="${2:-opus}"
        tail -f /home/"$CITIZEN"/logs/experience_*.jsonl 2>/dev/null || tail -f logs/*.log
        ;;
    *)
        echo "Experience v2"
        echo ""
        echo "  ./run.sh wake [citizen]           Single wake"
        echo "  ./run.sh loop [citizen]           Continuous loop"
        echo "  ./run.sh talk [citizen] [\"msg\"]   Interactive mode"
        echo "  ./run.sh status [citizen]         Show status"
        echo "  ./run.sh restore <citizen> [logs] Restore from v1"
        echo "  ./run.sh push                     Push to GitHub"
        echo "  ./run.sh sync                     Sync all from GitHub"
        echo "  ./run.sh logs [citizen]           Tail logs"
        ;;
esac
