#!/bin/bash
# Fix log files that have JSON entries without newlines

CITIZEN=${1:-opus}
LOG_DIR="/home/$CITIZEN/logs"

echo "Fixing logs for $CITIZEN in $LOG_DIR"

for f in "$LOG_DIR"/*.jsonl; do
    [ -f "$f" ] || continue
    
    # Check if file has newlines (more than 1 line)
    LINES=$(wc -l < "$f")
    SIZE=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f")
    
    if [ "$LINES" -lt 2 ] && [ "$SIZE" -gt 100 ]; then
        echo "  Fixing $f (was $LINES lines, $SIZE bytes)"
        
        # Split on }{ pattern and add newlines
        python3 << EOF
import re
with open("$f", "r") as fp:
    content = fp.read()

# Split JSON objects that are concatenated
# Pattern: }{  means end of one object, start of another
fixed = re.sub(r'\}\s*\{', '}\n{', content)

# Ensure ends with newline
if not fixed.endswith('\n'):
    fixed += '\n'

with open("$f", "w") as fp:
    fp.write(fixed)

# Count new lines
with open("$f", "r") as fp:
    lines = len(fp.readlines())
print(f"    Now {lines} entries")
EOF
    else
        echo "  OK: $f ($LINES entries)"
    fi
done

echo "Done!"
