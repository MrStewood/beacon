# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email security concerns to the maintainers
3. Include description, steps to reproduce, and potential impact

## Security Measures

### Data Handling
- All resource data is public information
- No user data is collected or stored
- No authentication required for read access
- No sensitive personal information in resource records

### XSS Prevention
- All resource data is HTML-escaped before insertion into DOM
- External links use `rel="noopener noreferrer"`
- No `eval()` or `innerHTML` with unescaped data
- Widget uses safe DOM construction

### Content Security
- No third-party scripts or tracking
- No external fonts or analytics
- No user data collection
- Static files only — no server-side processing

### URL Validation
- URLs must start with `http://` or `https://`
- No `javascript:` or `data:` URLs allowed
- Email addresses validated against basic pattern

### Build Security
- GitHub Actions runs in isolated environment
- No secrets in repository
- Dependencies pinned where possible
- Automated security checks in CI

## Data Accuracy

Resource data may contain errors. We:
- Mark confidence levels (high/medium/low)
- Track verification dates
- Encourage users to verify with providers
- Never claim data is complete or current

## Contact

For security concerns, contact the maintainers via GitHub.
