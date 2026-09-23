# Beacon Geographic Expansion Plan

## Strategy

Start at London, KY and grow outward in concentric waves. Each wave adds new counties/states. Within each area, prioritize high-need ZIPs first (Census need score > 60 = high need, > 35 = moderate).

## Expansion Waves

### Wave 0: London KY Epicenter (DONE)
Laurel County — ZIP 40744 and surrounding.
- ✅ 48 leads found, 1 investigated

### Wave 1: Immediate Neighbors (In Progress)
Counties bordering Laurel:

| Priority | County | State | ZIPs | High Need | Moderate |
|---|---|---|---|---|---|
| 1 | Knox | KY | 17 | 5 | 6 |
| 2 | Whitley | KY | 6 | 1 | 4 |
| 3 | Clay | KY | 5 | 1 | 3 |
| 4 | Pulaski | KY | 9 | 0 | 5 |
| 5 | McCreary | KY | 8 | 0 | 6 |
| 6 | Rockcastle | KY | 4 | 0 | 4 |

### Wave 2: Eastern KY Coalfield
High-need Appalachian counties:

| Priority | County | State | ZIPs | High Need |
|---|---|---|---|---|
| 1 | Harlan | KY | 27 | 1 |
| 2 | Leslie | KY | 18 | 3 |
| 3 | Floyd | KY | 22 | 2 |
| 4 | Letcher | KY | 15 | 1 |
| 5 | Perry | KY | 12 | 1 |
| 6 | Bell | KY | 10 | 0 |
| 7 | Owsley | KY | 4 | 1 |

### Wave 3: Central KY + TN Border
Expand to state capital region and Tennessee border:

| Priority | County | State | ZIPs |
|---|---|---|---|
| 1 | Fayette | KY | 30 |
| 2 | Jefferson | KY | 80 |
| 3 | Christian | KY | 20 |
| 4 | Clark | KY | 10 |
| 5 | Madison | KY | 12 |
| 6 | Davidson | TN | 60 |
| 7 | Knox | TN | 50 |

### Wave 4: Rest of Kentucky
All remaining KY counties.

### Wave 5: Tennessee
Border counties first, then statewide.

### Wave 6: Neighboring States
Virginia, West Virginia, Ohio, Indiana, Missouri, Illinois.

### Wave 7: Nationwide
Remaining states, prioritized by:
1. States with highest poverty rates
2. States with most uncovered ZIPs
3. Alphabetical fallback

## Priority Within Each County

1. **High-need ZIPs first** (Census need score > 60)
2. **Moderate-need ZIPs** (score 35-60)
3. **Low-need ZIPs** (score < 35)
4. **PO Box-only ZIPs last** (skip if no data)

## Progress Tracking

Track in `data/census/needs-analysis.json`:
- `zip_analysis[zip].researched` — true/false
- `zip_analysis[zip].investigated` — true/false
- `zip_analysis[zip].verified` — true/false

## Current Status

| Wave | Counties | ZIPs | Researched | Investigated | Verified |
|---|---|---|---|---|---|
| 0 | 1 | 6 | 1 | 1 | 0 |
| 1 | 6 | 49 | 0 | 0 | 0 |
| 2 | 7 | 108 | 0 | 0 | 0 |
| 3 | 7 | 262 | 0 | 0 | 0 |
| 4+ | TBD | ~32K | 0 | 0 | 0 |

## Director Workflow

Each heartbeat, the Director should:

1. Check current wave — which county/ZIP is next?
2. Check if Research Agent is idle — assign next ZIP
3. Check if any investigations are pending verification
4. Check if any verifications are ready for publishing
5. Report progress: "Wave 1: 3/49 ZIPs researched, 1 investigated"
