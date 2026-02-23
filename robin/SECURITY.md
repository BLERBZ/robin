# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| < 1.0   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Robin, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Email security concerns to the maintainers via GitHub's private vulnerability reporting
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Suggested fix (if any)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Assessment**: Within 5 business days
- **Fix timeline**: Depending on severity
  - Critical: 24-48 hours
  - High: 1 week
  - Medium: 2 weeks
  - Low: Next release

## Security Updates

- Security updates are released as patch versions
- Announced in GitHub releases with `[SECURITY]` prefix
- Critical updates trigger immediate release

## Security Best Practices

When using Robin:

- Keep your Python environment updated
- Use virtual environments
- Never commit `.env` files or API keys
- Review the `pip-audit` output in CI
- Use the latest release for production

## Scope

This security policy covers:
- The Robin codebase and its direct dependencies
- Official Robin releases and distributions
- The Robin GitHub repository

This policy does not cover:
- Third-party plugins or extensions
- User-modified versions of Robin
- Upstream dependencies (report those to their maintainers)
