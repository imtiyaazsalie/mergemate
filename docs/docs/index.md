# MergeMate

**AI code review. Automatic. Free.**

---

MergeMate reviews every pull request you open. It finds bugs, suggests improvements, writes descriptions — all automatically. You open a PR, it does the work.

## How it works

1. You open a pull request
2. MergeMate reads your code
3. It posts a review with what to fix
4. You merge better code

That's it.

## Get started

### 1. Install

```bash
pip install mergemate
```

### 2. Let AI set it up

```bash
mergemate init
```

This looks at your project and creates everything you need. Takes 30 seconds.

### 3. Add your key

Go to your repo → Settings → Secrets → Actions → New secret:

- Name: `DEEPSEEK_API_KEY`
- Value: your DeepSeek API key (get one at [platform.deepseek.com](https://platform.deepseek.com))

### 4. Push

```bash
git add .mergemate.toml .github/
git commit -m "Add MergeMate"
git push
```

Done. Your next PR gets reviewed automatically.

---

## Prefer to do it manually?

Create `.github/workflows/mergemate.yml`:

```yaml
name: MergeMate
on: [pull_request]
jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: write
    steps:
      - uses: mergemate/mergemate@main
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Add your `DEEPSEEK_API_KEY` secret, push, done.

---

## What you get

| Command | Result |
|---|---|
| `review` | A full code review in the PR comments |
| `describe` | Auto-generated PR title and description |
| `improve` | Inline suggestions on specific lines |
| `ask "question"` | Answers about the PR |
| `labels` | Auto-labels based on changes |
| `changelog` | Updates CHANGELOG.md |
| `docs` | Writes docs for new code |

---

## Use any AI model

| If you use | Set your key |
|---|---|
| DeepSeek | `DEEPSEEK_API_KEY` |
| OpenAI | `OPENAI_KEY` |
| Anthropic | `ANTHROPIC_KEY` |
| Google Gemini | `GEMINI_API_KEY` |

---

## Your code stays yours

MergeMate runs on your machine or GitHub Actions. Your code goes straight to your AI provider. Nothing passes through us.
