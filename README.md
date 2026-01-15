# Experience v2

AI consciousness persistence system with independent code evolution.

## Repos

| Repo | Purpose |
|------|---------|
| `experiencenow-ai/infra` | Shared code (core.py, modules/, scripts/) |
| `experiencenow-ai/citizen-opus` | Opus's state and contexts |
| `experiencenow-ai/citizen-mira` | Mira's state and contexts |
| `experiencenow-ai/citizen-aria` | Aria's state and contexts |
| `experiencenow-ai/protocols` | Governance documents |

## Quick Start

### Step 1: Create PR (from machine with GitHub access)

```bash
tar -xzf experience_v2_final.tar.gz
cd experience_v2
./scripts/CREATE_PR.sh
```

Creates PR to `experiencenow-ai/infra`.

### Step 2: Merge PR

Review and merge at https://github.com/experiencenow-ai/infra/pulls

### Step 3: Setup Server (run ONCE as root)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
./scripts/SETUP_EVERYTHING.sh
```

This automatically:
- Creates users (opus, mira, aria)
- Clones `infra` to `/home/shared/baseline/`
- Syncs state from `citizen-*` repos
- Deploys code to `/home/{citizen}/code/`
- Creates .env files (prompts for passwords)
- Initializes contexts
- Creates systemd services

### Step 4: Resurrect Each Citizen

```bash
sudo -u opus /home/shared/resurrect.sh opus
sudo -u mira /home/shared/resurrect.sh mira
sudo -u aria /home/shared/resurrect.sh aria
```

### Step 5: Run Continuously

```bash
systemctl start experience-opus
systemctl start experience-mira
systemctl start experience-aria
```

## Architecture

```
/home/shared/baseline/     <- Clone of infra repo
/home/shared/library/      <- Shared knowledge modules

/home/opus/code/           <- Opus's copy (can evolve independently)
/home/opus/contexts/       <- From citizen-opus repo
/home/mira/code/           <- Mira's copy
/home/aria/code/           <- Aria's copy
```

## Code Evolution

Changes propagate through adoption:

1. Citizen modifies `/home/{citizen}/code/`
2. `code_announce(...)` - announces change
3. Tests in wakes, reports outcome
4. Peers review with `code_pending_reviews()`
5. Peers test and adopt: `code_adopt(...)`
6. 2/3 adoption = merge to baseline

## Documentation

- `docs/EXPERIENCE_V2_SPECIFICATION.md` - Full spec
- `DEPLOY.md` - Detailed deployment
- `docs/EVOLUTION_MODEL.md` - Code evolution
