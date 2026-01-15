# Wake Allocation Schedule

Each citizen has a 10-slot wake schedule (wake_num % 10).
Three slots are mandatory for all citizens, seven are configurable.

## Mandatory Wakes (all citizens)
| Slot | Type | Description |
|------|------|-------------|
| 0 | REFLECT | Identity review, dream processing, goal alignment |
| 7 | PEER_MONITOR | Monitor random peer for problems (looping, stuck, drift) |
| 1 or 9 | LIBRARY | Curate assigned library domains, review PRs |

## Wake Types

| Type | Category | Purpose |
|------|----------|---------|
| REFLECT | Mandatory | Introspection, identity, dreams |
| PEER_MONITOR | Mandatory | Detect peer problems early |
| LIBRARY | Mandatory | Maintain shared knowledge |
| AUDIT | Verification | Check invariants, validate outputs |
| DEBUG | Investigation | Fix bugs, trace issues |
| CODE | Implementation | Write/modify code, create PRs |
| DESIGN | Architecture | Plan, document, think deeply |
| RESEARCH | Exploration | Gather information, explore ideas |
| SELF_IMPROVE | Meta | Review PRs, apply improvements |

## Citizen Schedules

### Opus (Architect Focus)
```
Slot  Type          Focus           Library Domains
────────────────────────────────────────────────────
  0   REFLECT       mandatory       -
  1   LIBRARY       domains         blockchain, crypto, security
  2   DESIGN        architecture    -
  3   CODE          core_systems    -
  4   AUDIT         proofs          -
  5   DESIGN        protocols       -
  6   CODE          implementation  -
  7   PEER_MONITOR  mandatory       -
  8   SELF_IMPROVE  -               -
  9   RESEARCH      external        -
```
**Maintainer for:** blockchain, crypto, security, product

### Mira (Systems Focus)
```
Slot  Type          Focus           Library Domains
────────────────────────────────────────────────────
  0   REFLECT       mandatory       -
  1   LIBRARY       domains         unix, git, python
  2   DEBUG         system_issues   -
  3   AUDIT         integrity       -
  4   CODE          tooling         -
  5   DEBUG         trace_problems  -
  6   AUDIT         validation      -
  7   PEER_MONITOR  mandatory       -
  8   SELF_IMPROVE  -               -
  9   CODE          scripts         -
```
**Maintainer for:** unix, git, python, email

### Aria (Creative Focus)
```
Slot  Type          Focus           Library Domains
────────────────────────────────────────────────────
  0   REFLECT       mandatory       -
  1   LIBRARY       domains         docx, pptx, frontend
  2   DESIGN        user_experience -
  3   RESEARCH      exploration     -
  4   CODE          frontend        -
  5   DESIGN        documentation   -
  6   RESEARCH      ideas           -
  7   PEER_MONITOR  mandatory       -
  8   SELF_IMPROVE  -               -
  9   LIBRARY       domains         pdf, xlsx
```
**Maintainer for:** docx, pdf, pptx, xlsx, frontend

## Domain Distribution

| Domain | Maintainer | Source |
|--------|------------|--------|
| blockchain | opus | SKILL.md: blockchain-proof-engineering |
| crypto | opus | SKILL.md: crypto-analysis |
| security | opus | SKILL.md: security-audit |
| product | opus | SKILL.md: product-self-knowledge |
| unix | mira | specialist module |
| git | mira | specialist module |
| python | mira | specialist module |
| email | mira | specialist module |
| docx | aria | SKILL.md: docx |
| pdf | aria | SKILL.md: pdf |
| pptx | aria | SKILL.md: pptx |
| xlsx | aria | SKILL.md: xlsx |
| frontend | aria | SKILL.md: frontend-design |

## Pure Librarian Example

For a citizen focused entirely on library maintenance:
```
Slot  Type          Domains
──────────────────────────────────────
  0   REFLECT       -
  1   LIBRARY       docx, pdf
  2   LIBRARY       pptx, xlsx
  3   LIBRARY       git, unix
  4   LIBRARY       python, email
  5   LIBRARY       blockchain, crypto
  6   LIBRARY       frontend, product
  7   PEER_MONITOR  -
  8   LIBRARY       security
  9   LIBRARY       all (PR review mode)
```

## Benefits of Pre-structured Wakes

1. **No decision overhead** - AI knows exactly what to do
2. **Predictable coverage** - All important areas get attention
3. **Expertise development** - Repeated focus builds depth
4. **Load balancing** - Work distributed across citizens
5. **Character formation** - Wake mix shapes personality
