# Security Policy

## Reporting a Vulnerability

**Do NOT open a public issue for security vulnerabilities.**

Instead, report security issues via:
- GitHub Security Advisories: https://github.com/AnuAnu22/Serin/security/advisories/new
- Or email: fakef5858@gmail.com

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

## Response Timeline

- **Initial response:** Within 48 hours
- **Triage and validation:** Within 7 days
- **Fix and disclosure:** Coordinated with reporter

## Supported Versions

Only the latest commit on `main` is actively supported. Security fixes are not backported to older commits.

## Security Scanning

This repository uses:
- `bandit` for Python security issues
- `detect-secrets` for accidental secret commits
- `pip-audit` and `osv-scanner` for dependency vulnerabilities
- GitHub Dependabot alerts

All PRs must pass security scans before merge.

## Security Best Practices for Contributors

### Secrets and Credentials

- Never commit secrets, API keys, or tokens
- Use environment variables for sensitive configuration
- Run `detect-secrets scan` before committing if unsure

### Dependencies

- Review new dependencies for security issues
- Check licenses and maintenance status
- Use exact versions in `pyproject.toml`

### Code

- Validate all user inputs
- Use parameterized queries for database operations
- Avoid `eval()`, `exec()`, and other dangerous functions
- Sanitize data before logging or display

### Disclosures

If you discover a security issue in a dependency:
1. Check if it's already reported (GitHub Dependabot alerts)
2. If not, report it to the dependency maintainer
3. Coordinate disclosure timeline with the maintainer
4. Open a PR to update the dependency once a fix is available
