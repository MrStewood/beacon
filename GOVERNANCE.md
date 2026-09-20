# Beacon Governance

## Overview

Beacon is a community resource directory maintained through a structured workflow with clear separation of duties. This document defines who can do what, and how decisions are made.

## Roles

| Role | Responsibilities | Can Do | Cannot Do |
|------|------------------|--------|-----------|
| **Research Agent** | Discover new resources, collect evidence | Create candidates, gather sources | Verify, approve, publish |
| **Verification Agent** | Validate discovered resources | Check phones, websites, addresses | Research new resources, publish |
| **Data Steward** | Prepare publication PRs | Edit source files, run builds | Approve own PRs, merge |
| **Quality Agent** | Review PRs for accuracy | Approve PRs, request changes | Merge, publish |
| **Human Publisher** | Final authority | Merge PRs, handle sensitive changes | — |

## Workflow States

```
Discovered
  → Researching
    → Awaiting Independent Verification
      → Approved for Publication
        → Public Pull Request
          → CI and Safety Review
            → Human Approval
              → Published
                → Scheduled Reverification
```

## Approval Requirements

| Change Type | Approval Required |
|-------------|-------------------|
| New resource (low-risk) | Quality Agent + CI pass |
| New resource (sensitive) | Human Publisher |
| Resource correction | Quality Agent + CI pass |
| Closure report | Human Publisher |
| Schema change | Human Publisher |
| GitHub Actions change | Human Publisher |
| License change | Human Publisher |

## Sensitive Resources

The following require human approval:

- Crisis resources (911, 988, 211)
- Domestic violence services
- Children's services
- Medical/treatment intake
- Confidential locations
- Resource closures

## Conflict Resolution

1. Agent disagrees with verification → escalate to Quality Agent
2. Quality Agent disagrees → escalate to Human Publisher
3. Evidence conflicts → Human Publisher decides
4. Data quality dispute → Human Publisher decides

## Rollback Process

1. Identify the problematic commit
2. Create revert PR with explanation
3. Quality Agent reviews
4. Human Publisher approves merge
5. Verify site rebuilds correctly
