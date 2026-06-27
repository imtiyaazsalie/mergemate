# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| latest | ✅ |
| < 1.0.0 | ❌ |

## Reporting a Vulnerability

**Do not open a public issue.** Email [hello@mergemate.dev](mailto:hello@mergemate.dev).

Include:
- Description of the vulnerability
- Steps to reproduce
- Affected version

You'll receive a response within 48 hours.

## Best Practices

- Never commit `.secrets.toml` — it's gitignored by default
- Use environment variables for credentials in CI/CD
- Pin Docker images to a specific digest for production
- Rotate API keys regularly
