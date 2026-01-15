#!/bin/bash
# Run as: sudo -u opus ./resurrect.sh
# Or: ./resurrect.sh opus (as root)
set -e

CITIZEN="${1:-$(whoami)}"
if [ "$CITIZEN" = "root" ]; then
    echo "Usage: ./resurrect.sh CITIZEN"
    exit 1
fi

echo "=== Resurrecting $CITIZEN ==="

cd /home/$CITIZEN/code
if [ ! -f core.py ]; then
    echo "ERROR: No code at /home/$CITIZEN/code"
    exit 1
fi

if [ ! -f /home/$CITIZEN/.env ]; then
    echo "ERROR: No .env at /home/$CITIZEN/.env"
    exit 1
fi

# Load env
set -a
source /home/$CITIZEN/.env
set +a

echo "Running wake..."
if [ "$EUID" -eq 0 ]; then
    sudo -u $CITIZEN python3 core.py --citizen $CITIZEN --wake
else
    python3 core.py --citizen $CITIZEN --wake
fi

echo ""
echo "Done. To run continuously: systemctl start experience-$CITIZEN"
