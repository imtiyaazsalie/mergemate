# Security Policy

## Supported Versions

MergeMate is under active development. Security updates are provided for the latest release.

### Docker Deployment

For the most recent updates, use the latest Docker image:

```yaml
uses: mergemate/mergemate@main
```

For a fixed version, pin to a specific release:

```yaml
steps:
  - name: MergeMate action step
    uses: docker://mergemate/mergemate:latest
```

## Reporting a Vulnerability

If you discover a security vulnerability, please report it to:

Email: [your-email@example.com]

Please include:
- Description of the vulnerability
- Steps to reproduce
- Affected MergeMate version

We take all security reports seriously and will respond promptly.
