# GitHub Integration

## Quickest way

```bash
pip install mergemate
mergemate init
```

This auto-creates `.mergemate.toml` and `.github/workflows/mergemate.yml`. Just add your API key secret and push.

## Manual setup

### 1. Create the workflow

Put this in `.github/workflows/mergemate.yml`:

```yaml
name: MergeMate
on:
  pull_request:
    types: [opened, synchronize]
  issue_comment:
    types: [created]
jobs:
  review:
    if: ${{ github.event.sender.type != 'Bot' }}
    runs-on: ubuntu-latest
    permissions:
      issues: write
      pull-requests: write
      contents: write
    steps:
      - uses: mergemate/mergemate@main
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          config.model: "deepseek/deepseek-chat"
```

### 2. Add your API key

Repo → Settings → Secrets → Actions → New secret:

- Name: `DEEPSEEK_API_KEY`
- Value: your key from [platform.deepseek.com](https://platform.deepseek.com)

### 3. Push

```bash
git add .github/workflows/mergemate.yml
git commit -m "Add MergeMate"
git push
```

### 4. Open a PR

MergeMate posts a review. Comment `/describe`, `/improve`, or `/ask "question"` on the PR for more.

---

## Using other AI models

Swap the env vars:

| Model | Set this |
|---|---|
| DeepSeek | `DEEPSEEK_API_KEY` |
| OpenAI | `OPENAI_KEY` |
| Anthropic | `ANTHROPIC_KEY` |
| Google Gemini | `GEMINI_API_KEY` |

And update `config.model`:

```yaml
# DeepSeek (default)
config.model: "deepseek/deepseek-chat"

# OpenAI
config.model: "gpt-4o"

# Anthropic
config.model: "claude-sonnet-4-20250514"
```

---

## Advanced: trigger specific tools automatically

```yaml
env:
  github_action_config.auto_review: "true"
  github_action_config.auto_describe: "true"
  github_action_config.auto_improve: "true"
```

[Full config options →](../usage-guide/configuration_options.md)
