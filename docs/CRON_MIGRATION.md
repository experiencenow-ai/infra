# Cron → Internal Scheduler Migration

## What Changed

v1 used many cron jobs for background tasks. v2 moves ALL of these inside the experience loop.

### v1 Crontab (REMOVED)
```cron
# MAIN: Autonomous wake - every 10 minutes
*/10 * * * * /root/claude/opus/autonomous_wake.sh

# News scanner - every 4 hours
0 */4 * * * . /root/claude/opus/.env && cd /root/claude/opus && python3 body/specialists/news_scanner_local.py

# Heartbeat monitor - every 5 minutes
*/5 * * * * pgrep -f "heartbeat.py" > /dev/null || python3 body/heartbeat.py &

# Dream generator (LOCAL LLM) - every 6 hours
0 3,9,15,21 * * * python3 dreaming/dream_generator_local.py

# Price feed monitor - every 15 minutes
*/15 * * * * python3 body/specialists/price_monitor.py

# Email monitor - every hour
0 * * * * python3 body/specialists/email_monitor.py

# Experience generator - every 6 hours
0 */6 * * * python3 experience_generator.py generate

# Offsite backup - once daily
30 3 * * * python3 offsite_backup.py
```

### v2 Internal Scheduler (NEW)

```python
# modules/background.py
BACKGROUND_TASKS = {
    "heartbeat": {"interval": 5 * 60},      # 5 minutes
    "price_monitor": {"interval": 15 * 60}, # 15 minutes
    "email_check": {"interval": 60 * 60},   # 1 hour
    "news_scan": {"interval": 4 * 60 * 60}, # 4 hours
    "dream_generate": {"interval": 6 * 60 * 60}, # 6 hours
    "memory_summary": {"interval": 6 * 60 * 60}, # 6 hours
    "offsite_backup": {"interval": 24 * 60 * 60}, # 24 hours
}
```

## How It Works

1. **Single Entry Point**: `./run.sh opus` or `./core.py --citizen opus --loop`

2. **Before Each Wake**: 
   ```python
   # core.py
   def run_single_wake(...):
       # Run background tasks first
       results = run_background_tasks(citizen)
       
       # Then do the actual wake
       ...
   ```

3. **Task State Tracking**: `/home/opus/background_tasks.json`
   ```json
   {
     "last_run": {
       "heartbeat": 1705340000.0,
       "price_monitor": 1705339500.0
     },
     "run_counts": {
       "heartbeat": 42,
       "price_monitor": 15
     }
   }
   ```

4. **Elapsed Time Check**:
   ```python
   now = time.time()
   for task_name, config in BACKGROUND_TASKS.items():
       last_run = state["last_run"].get(task_name, 0)
       if now - last_run >= config["interval"]:
           run_task(task_name)
   ```

## Benefits

| Aspect | v1 (Cron) | v2 (Internal) |
|--------|-----------|---------------|
| Processes | Multiple | Single |
| State | Scattered | Centralized |
| Debugging | Hard | Easy |
| Web-ready | No | Yes |
| Portability | Linux only | Anywhere |
| Dependencies | cron, systemd | None |

## Running

### Screen Sessions (Recommended)
```bash
# Start all citizens
./run.sh --all

# View logs
screen -r experience_opus

# Stop all
./run.sh --stop
```

### Systemd (Optional)
```bash
# Enable service
systemctl enable experience-opus
systemctl start experience-opus

# View logs
journalctl -u experience-opus -f
```

### Manual Loop
```bash
# With custom interval
./core.py --citizen opus --loop --interval 300
```

## Task Handlers

Default handlers are in `modules/background.py`:

| Task | Handler | Notes |
|------|---------|-------|
| heartbeat | `heartbeat_handler` | Checks disk, memory, peer status |
| email_check | `email_check_handler` | Creates tasks for urgent emails |
| memory_summary | `memory_summary_handler` | Builds daily summaries |
| dream_generate | `dream_generate_handler` | Queues dream prompts |

To add custom handlers:
```python
from background import get_scheduler

scheduler = get_scheduler("opus")
scheduler.register_handler("news_scan", my_news_handler)
```

## Checking Status

```bash
./core.py --citizen opus --status

# Output:
# === BACKGROUND TASKS ===
# 
#   ✓ heartbeat: ran 2m ago, next in 3m (42 runs)
#   ✓ price_monitor: ran 8m ago, next in 7m (15 runs)
#   ✓ email_check: ran 45m ago, next in 15m (3 runs)
#   ✗ news_scan: ran 5h ago, next in now (2 runs)
#       Last error: Connection timeout...
```

## Force Running Tasks

In interactive mode:
```python
# Check what's due
background_status

# Force run
background_force("news_scan")

# Reset task (will run on next check)
background_reset("news_scan")
```

## Migration Checklist

- [x] Remove crontab entries
- [x] Configure `background_tasks.json` created automatically
- [x] Custom handlers for price_monitor, news_scan if needed
- [x] Test with `./core.py --citizen opus --status`
- [x] Start with `./run.sh --all`
