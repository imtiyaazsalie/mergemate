# MergeMate

**AI code review that lives in your pull requests.**

---

MergeMate watches your pull requests and gives you honest, actionable feedback. It reads the diff, thinks about what changed, and tells you what matters — bugs, improvements, missing tests, confusing patterns.

## What it does

| Command | One-line |
|---|---|
| `review` | Full code review posted as a PR comment |
| `describe` | Generates a PR title and description from the diff |
| `improve` | Inline suggestions on specific lines of code |
| `ask` | Answer any question about the PR in context |
| `labels` | Auto-label PRs based on what changed |
| `docs` | Write documentation for new or changed code |
| `changelog` | Update your CHANGELOG from PR contents |
| `similar` | Find issues related to this PR |

## Start in 60 seconds

```bash
pip install mergemate
export DEEPSEEK_API_KEY="sk-..."
export GITHUB_TOKEN="ghp_..."

mergemate --pr_url https://github.com/you/repo/pull/42 review
```

That's it. The review appears as a comment on your PR.

## Or run it on every PR

Drop this in `.github/workflows/mergemate.yml`:

```yaml
name: MergeMate
on: [pull_request]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: mergemate/mergemate@main
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Now every PR gets reviewed automatically.

## Works with

- **GitHub** — Action, App, or CLI
- **GitLab** — Webhook, CI pipeline, or CLI
- **Bitbucket** — Pipeline or CLI
- **Azure DevOps** — Pipeline or CLI
- **Gitea** — Webhook or CLI

## Pick your model

| Provider | Model |
|---|---|
| DeepSeek | `deepseek/deepseek-chat` |
| OpenAI | `gpt-4o` |
| Anthropic | `claude-sonnet-4-20250514` |
| Google | `gemini/gemini-2.5-flash` |
| Local | `ollama/llama3` |

## Self-hosted, always

MergeMate runs on your machine or your CI. Your code never leaves your infrastructure.
API calls go directly from you to your AI provider. No middleman, no telemetry, no accounts.
