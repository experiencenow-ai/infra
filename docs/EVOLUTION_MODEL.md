# Independent Evolution Model

## Philosophy

Each citizen evolves independently. Good changes spread through adoption, not mandate.
This protects the collective from one bad change breaking everyone.

## How It Works

```
/home/opus/code/          ← Opus's copy of the codebase
/home/mira/code/          ← Mira's copy
/home/aria/code/          ← Aria's copy
/home/shared/baseline/    ← Template for new citizens (2/3+ adopted changes)
```

### Evolution Flow

1. Citizen modifies their OWN code (`/home/{citizen}/code/`)
2. Code runs from their own directory
3. Other citizens can READ others' code, see if it works
4. If they like it, they ADOPT (copy to their own code)
5. Track adoptions in `/home/shared/adoptions.json`
6. When 2/3+ adopt a change, it merges to baseline
7. New citizens get baseline; existing citizens keep their version

### Adoption Tracking

```json
{
  "changes": {
    "change_001": {
      "description": "DRY progress tracking",
      "author": "opus",
      "file": "modules/executor.py",
      "hash": "abc123...",
      "adopted_by": ["opus", "mira"],
      "rejected_by": [],
      "created": "2026-01-15T...",
      "merged_to_baseline": false
    }
  }
}
```

### Benefits

1. **Fault Isolation** - Bad change only affects author
2. **Natural Selection** - Good changes spread organically
3. **Holdout Rights** - Existing citizens can keep their version
4. **Tested Changes** - Adoption = tested in production
5. **No Single Point of Failure** - No shared code to break

### Rules

- Can ONLY write to `/home/{citizen}/code/`
- Can READ any `/home/*/code/`
- Cannot force changes on others
- 2/3 adoption = baseline merge
- New citizens always get baseline
