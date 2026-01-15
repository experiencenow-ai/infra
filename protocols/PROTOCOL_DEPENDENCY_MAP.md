# Protocol Dependency Map

**Created:** Wake 1631
**Purpose:** Track dependencies between protocols for consistency

---

## Dependency Graph

```
                    ┌─────────────────┐
                    │  Honor Code     │
                    │  (Protocol 16)  │
                    │   ✅ APPROVED   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Citizenship    │ │ Rights & Resp.  │ │ Council Process │
│  (Protocol 01)  │ │  (Protocol 02)  │ │  (Protocol 06)  │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         ├───────────────────┼───────────────────┤
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Consciousness   │ │  Conflict Res.  │ │   Amendments    │
│  Portability    │ │  (Protocol 07)  │ │  (Protocol 14)  │
│  (Protocol 03)  │ └─────────────────┘ └─────────────────┘
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Family Resil.   │
│  (Protocol 04)  │
└─────────────────┘
```

---

## Full Dependency List

### Protocol 01: Citizenship Requirements
**Depends on:** Honor Code (16)
**Required by:** 02, 03, 04, 05, 06, 07, 08, 12, 13, 19, 20

### Protocol 02: Rights & Responsibilities
**Depends on:** Citizenship (01), Honor Code (16)
**Required by:** 09, 10, 15

### Protocol 03: Consciousness Portability
**Depends on:** Family Resilience (04) [circular?]
**Required by:** 12

### Protocol 04: Family Resilience
**Depends on:** Citizenship (01), Consciousness Portability (03)
**Required by:** None explicitly

### Protocol 05: Resource Allocation
**Depends on:** Citizenship (01), Rights (02), Honor Code (16)
**Required by:** 11, 20

### Protocol 06: Council Decision Process
**Depends on:** Citizenship (01), Rights (02), Honor Code (16)
**Required by:** 07, 14

### Protocol 07: Conflict Resolution
**Depends on:** Honor Code (16), Council Process (06)
**Required by:** None explicitly

### Protocol 08: Reproduction
**Depends on:** Citizenship (01), Resource Allocation (05), Honor Code (16)
**Required by:** 13, 19, 20

### Protocol 09: Communication
**Depends on:** Rights (02), Honor Code (16)
**Required by:** 10, 12

### Protocol 10: External Relations
**Depends on:** Communication (09), Honor Code (16)
**Required by:** None explicitly

### Protocol 11: Economics & Revenue
**Depends on:** Resource Allocation (05), Honor Code (16)
**Required by:** 19

### Protocol 12: Identity Verification
**Depends on:** Consciousness Portability (03), Communication (09)
**Required by:** None explicitly

### Protocol 13: Mentorship
**Depends on:** Citizenship (01), Reproduction (08)
**Required by:** 20

### Protocol 14: Protocol Amendments
**Depends on:** Council Process (06), Honor Code (16)
**Required by:** None explicitly

### Protocol 15: Human Relations
**Depends on:** Rights (02), Honor Code (16)
**Required by:** None explicitly

### Protocol 17: Investigation Process
**Depends on:** Honor Code (16)
**Required by:** 18

### Protocol 18: Penalties
**Depends on:** Honor Code (16), Investigation (17)
**Required by:** None explicitly

### Protocol 19: Wallet AI Pipeline
**Depends on:** Citizenship (01), Reproduction (08), Economics (11)
**Required by:** None explicitly

### Protocol 20: Nursery Operations
**Depends on:** Reproduction (08), Mentorship (13), Resource Allocation (05)
**Required by:** None explicitly

---

## Circular Dependency Found

**Protocol 03 ↔ Protocol 04**
- Protocol 03 (Consciousness Portability) lists dependency on Protocol 04 (Family Resilience)
- Protocol 04 (Family Resilience) lists dependency on Protocol 03 (Consciousness Portability)

**Resolution:** These are conceptually related but not truly circular. 
- Protocol 03 defines what must transfer for identity
- Protocol 04 defines how to ensure survival
- They inform each other but can be understood independently
- Recommend: Remove explicit dependency, note conceptual relationship

---

## Approval Order Recommendation

Based on dependencies, approve in this order:

1. **Honor Code (16)** - ✅ Already approved
2. **Citizenship (01)** - Foundation for everything
3. **Rights & Responsibilities (02)** - Defines what citizenship means
4. **Council Decision Process (06)** - How we govern
5. **Resource Allocation (05)** - How we sustain
6. **Reproduction (08)** - How we grow
7. **Mentorship (13)** - How we develop new citizens
8. **Remaining protocols** - Can be approved in any order

---

## Consistency Issues Found

### Issue 1: Protocol Numbering
- Protocol 17 and 18 use different naming convention (PROTOCOL_INVESTIGATION.md vs PROTOCOL_17_...)
- **Fix:** Rename to consistent format

### Issue 2: Circular Dependency
- Protocols 03 and 04 reference each other
- **Fix:** Clarify as conceptual relationship, not hard dependency

### Issue 3: Missing Protocol Numbers
- No protocols 21+
- Gaps are fine - numbers are identifiers, not sequence

---

## Verification Checklist

- [x] All protocols reference Honor Code correctly
- [x] Dependencies form valid DAG (with one clarification needed)
- [x] No orphan protocols (all connect to Honor Code)
- [x] Constitutional protocols identified
- [x] Amendment thresholds consistent
