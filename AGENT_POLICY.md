# Beacon Agent Policy

## Overview

This policy governs how Paperclip agents interact with the Beacon repository. All agents must comply with these rules.

## Agent Workflow

1. Agent receives a task from Paperclip
2. Agent creates a feature branch
3. Agent works on the branch (research, verify, prepare)
4. Agent opens a pull request
5. CI validates the changes
6. Human reviews and approves
7. Human merges to main

## Prohibited Actions

Agents must never:
- Push directly to `main`
- Merge their own pull requests
- Approve their own pull requests
- Bypass CI validation
- Modify governance files
- Modify GitHub Actions workflows
- Access private information
- Store credentials in the repository
- Invent missing information
- Mark resources closed without evidence

## Evidence Requirements

Every resource change must include:
- Source URL where information was found
- Date the source was checked
- Source type (official-provider, government, etc.)
- What fields the source supports

## Separation of Duties

- Research agent discovers resources
- Verification agent validates them (must be different agent)
- Data steward prepares the PR
- Quality agent reviews
- Human approves and merges

## Sensitive Resources

The following require human approval:
- Crisis resources (911, 988, 211)
- Domestic violence services
- Children's services
- Medical/treatment providers
- Confidential locations
