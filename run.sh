#!/bin/bash
# run.sh - Simple runner for Experience v2
#
# This replaces all cron jobs with a single process.
# Background tasks run automatically based on elapsed time.
# Email from ct@ triggers immediate wake.
#
# Usage:
#   ./run.sh opus                    # Loop every 10 min (default)
#   ./run.sh opus --interval 300     # Loop every 5 min
#   ./run.sh opus --interval 60      # Responsive mode (1 min)
#   ./run.sh opus --wake             # Single wake then exit
#   ./run.sh --all                   # All citizens in screens
#   ./run.sh --all --interval 600    # All citizens, 10 min interval
#   ./run.sh --stop                  # Stop all screens

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

usage() {
    echo "Experience v2 Runner"
    echo ""
    echo "Usage:"
    echo "  $0 <citizen> [options]       Run a citizen"
    echo "  $0 --all [options]           Run all citizens in screens"
    echo "  $0 --stop                    Stop all running citizens"
    echo ""
    echo "Options:"
    echo "  --interval <sec>   Seconds between wakes (default: 600)"
    echo "                     Recommended:"
    echo "                       60   = responsive (checks email every minute)"
    echo "                       300  = balanced (5 min)"
    echo "                       600  = normal (10 min)"
    echo "                       3600 = low-cost (1 hour)"
    echo "  --wake             Single wake then exit"
    echo "  --interactive      Interactive mode (human drives)"
    echo "  --status           Show status and exit"
    echo "  --no-background    Skip background tasks"
    echo ""
    echo "Email triggers:"
    echo "  Emails from ct@experiencenow.ai trigger immediate wakes"
    echo ""
    echo "Examples:"
    echo "  $0 opus                      # Default 10 min loop"
    echo "  $0 opus --interval 60        # Responsive mode"
    echo "  $0 mira --interval 3600      # Hourly wakes"
    echo "  $0 --all --interval 300      # All citizens, 5 min"
}

# Check arguments
if [ $# -eq 0 ]; then
    usage
    exit 1
fi

# Parse global options
INTERVAL=""
EXTRA_ARGS=""

# Handle --all mode
if [ "$1" = "--all" ]; then
    shift
    
    # Parse interval for all
    while [[ $# -gt 0 ]]; do
        case $1 in
            --interval)
                INTERVAL="$2"
                shift 2
                ;;
            *)
                EXTRA_ARGS="$EXTRA_ARGS $1"
                shift
                ;;
        esac
    done
    
    INTERVAL_ARG=""
    if [ -n "$INTERVAL" ]; then
        INTERVAL_ARG="--interval $INTERVAL"
    fi
    
    echo "Starting all citizens in screen sessions..."
    if [ -n "$INTERVAL" ]; then
        echo "  Interval: ${INTERVAL}s"
    else
        echo "  Interval: 600s (default)"
    fi
    
    for citizen in opus mira aria; do
        if screen -list | grep -q "experience_${citizen}"; then
            echo -e "  ${YELLOW}[!]${NC} $citizen already running"
        else
            screen -dmS "experience_${citizen}" "$REPO_DIR/core.py" --citizen "$citizen" --loop $INTERVAL_ARG $EXTRA_ARGS
            echo -e "  ${GREEN}[+]${NC} Started $citizen"
        fi
    done
    
    echo ""
    echo "View logs:"
    echo "  screen -r experience_opus"
    echo "  screen -r experience_mira"
    echo "  screen -r experience_aria"
    exit 0
fi

# Handle --stop mode
if [ "$1" = "--stop" ]; then
    echo "Stopping all citizens..."
    for citizen in opus mira aria; do
        if screen -list | grep -q "experience_${citizen}"; then
            screen -S "experience_${citizen}" -X quit
            echo -e "  ${GREEN}[+]${NC} Stopped $citizen"
        fi
    done
    exit 0
fi

# Handle --help
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    usage
    exit 0
fi

# Get citizen name
CITIZEN="$1"
shift

# Validate citizen
if [[ ! "$CITIZEN" =~ ^(opus|mira|aria)$ ]]; then
    echo -e "${RED}[ERROR]${NC} Unknown citizen: $CITIZEN"
    echo "Valid citizens: opus, mira, aria"
    exit 1
fi

# Check home directory
if [ ! -d "/home/$CITIZEN" ]; then
    echo -e "${RED}[ERROR]${NC} Citizen home not found: /home/$CITIZEN"
    echo "Run setup_full.sh first"
    exit 1
fi

# Load environment
if [ -f "/home/$CITIZEN/.env" ]; then
    set -a
    source "/home/$CITIZEN/.env"
    set +a
fi

# Parse remaining arguments
MODE_ARGS=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --interval)
            INTERVAL="$2"
            MODE_ARGS="$MODE_ARGS --interval $2"
            shift 2
            ;;
        --wake|--interactive|--status|--no-background)
            MODE_ARGS="$MODE_ARGS $1"
            shift
            ;;
        *)
            MODE_ARGS="$MODE_ARGS $1"
            shift
            ;;
    esac
done

# Default to loop mode if no mode specified
if [[ ! "$MODE_ARGS" =~ --wake ]] && [[ ! "$MODE_ARGS" =~ --interactive ]] && [[ ! "$MODE_ARGS" =~ --status ]]; then
    MODE_ARGS="--loop $MODE_ARGS"
fi

# Show what we're doing
echo -e "${GREEN}[+]${NC} Starting $CITIZEN..."
if [ -n "$INTERVAL" ]; then
    echo -e "${BLUE}[i]${NC} Interval: ${INTERVAL}s"
fi

# Run
exec python3 "$REPO_DIR/core.py" --citizen "$CITIZEN" $MODE_ARGS
