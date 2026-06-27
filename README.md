# MergeMate

AI-powered pull request review and automation.

---

MergeMate automates code review workflows by providing AI-generated feedback, suggestions, and documentation for pull requests. It integrates with major git providers and supports multiple AI models.

## Why MergeMate?

- **Fast & Efficient**: Each tool (`/review`, `/improve`, `/ask`) uses a single LLM call
- **Handles Any PR Size**: Built-in compression strategy processes both small and large PRs
- **Highly Customizable**: Configuration-driven behavior via `.mergemate.toml`
- **Platform Agnostic**: GitHub, GitLab, Bitbucket, Azure DevOps, Gitea
- **Multi-Model Support**: OpenAI, Claude, Deepseek, and more
- **Self-Hosted**: Full control over your data and infrastructure

## Quick Start

### GitHub Action

```yaml
# .github/workflows/mergemate.yml
name: MergeMate
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: mergemate/mergemate@main
        env:
          OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### CLI

```bash
pip install mergemate
export OPENAI_KEY=your_key_here
mergemate --pr_url https://github.com/owner/repo/pull/123 review
```

### Docker

```bash
docker run -e OPENAI_KEY=$OPENAI_KEY \
  mergemate/mergemate review \
  --pr_url https://github.com/owner/repo/pull/123
```

## Features

| Tool | Description |
|---|---|
| `/review` | Comprehensive PR review with inline suggestions |
| `/describe` | Auto-generate PR title and description |
| `/improve` | Code suggestions as review comments |
| `/ask` | Ask questions about the PR in context |
| `/update_changelog` | Update CHANGELOG based on PR contents |
| `/add_docs` | Generate documentation for changed code |
| `/generate_labels` | Auto-label PRs based on content |
| `/similar_issue` | Find related issues |

### Platform Support

| | GitHub | GitLab | Bitbucket | Azure DevOps | Gitea |
|---|---|---|---|---|---|
| Review | ✅ | ✅ | ✅ | ✅ | ✅ |
| Describe | ✅ | ✅ | ✅ | ✅ | ✅ |
| Improve | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ask | ✅ | ✅ | ✅ | ✅ | |
| CLI | ✅ | ✅ | ✅ | ✅ | ✅ |
| Webhook/App | ✅ | ✅ | ✅ | ✅ | ✅ |

## Core Capabilities

- **PR Compression**: Adaptive file patch fitting for any PR size
- **Dynamic Context**: Automatically gather relevant project context
- **Ticket Context**: Fetch linked issue/ticket information
- **Interactivity**: Respond to comments and follow-up questions
- **Self-Reflection**: Review and improve its own output
- **Multi-Model**: Switch between AI providers via configuration

## Configuration

MergeMate is configured via `.mergemate.toml` in your repository root. See `mergemate/settings/configuration.toml` for all available options.

```toml
[config]
model = "gpt-4"
git_provider = "github"

[pr_reviewer]
extra_instructions = "Focus on security and performance"
```

## Data Privacy

MergeMate is self-hosted — your code never leaves your infrastructure. API calls go directly from your deployment to your chosen AI provider (OpenAI, Anthropic, etc.).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

Proprietary. All rights reserved.
