# Beacon Privacy and Safety Policy

## Public Data Principles

The public Beacon repository contains only information that:
- Is publicly available from official sources
- Has been verified or flagged as unverified
- Does not identify individuals seeking services
- Does not expose confidential locations

## Prohibited Data

The public repository must never contain:

- Personal information about people seeking services
- Private provider correspondence
- Call recordings or transcripts
- Confidential shelter addresses
- Unverified accusations
- Speculative closure claims
- Internal security details
- API keys or agent credentials

## Confidential Locations

某些服务提供者（如 DV 庇护所）的物理位置是保密的。

Rules:
- Never geocode confidential locations
- Never display confidential addresses publicly
- Mark as `location_type: confidential`
- Set `publicly_displayed: false`
- Only reference by name and phone

## Sensitive Resource Handling

### Crisis Resources (911, 988, 211)
- Never remove from directory
- Changes require human approval
- Always maintain current contact info

### Domestic Violence Services
- Do not publish shelter addresses
- Use general area references only
- Verify with provider before any change

### Children's Services
- Extra verification required
- Human approval for all changes
- Verify licensing status

### Medical/Treatment
- Verify provider credentials
- Confirm insurance acceptance
- Human approval for intake changes

## Incident Response

If private data is accidentally published:
1. Immediately create revert PR
2. Notify repository owner
3. Document the incident
4. Review and update controls

## Agent Restrictions

Agents must not:
- Access private medical records
- Contact individuals seeking services
- Share provider correspondence publicly
- Store credentials in repository
- Bypass verification requirements
