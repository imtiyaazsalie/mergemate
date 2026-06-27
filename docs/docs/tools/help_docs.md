# Help Docs

**Answers questions by searching your project's documentation folder — READMEs, guides, API docs, whatever lives under `/docs`.**

```
/help_docs "How do I configure the retry policy for the HTTP client?"
```

MergeMate pulls files from the docs directory, feeds them to the model as context, and replies with a direct answer.


## Pointing at a different repo

By default the tool reads docs from the repo that triggered the command. Override it to answer questions about another project:

```
/help_docs "What's the auth setup for the billing service?" --pr_help_docs.repo_url="https://github.com/owner/billing-service" --pr_help_docs.docs_path="docs"
```

## Configuration

(`[pr_help_docs]` section)

| Option | Default | Notes |
|---|---|---|
| `repo_url` | `""` | Override to read docs from a different repository. |
| `docs_path` | `"docs"` | Relative path to the documentation folder. |
| `repo_default_branch` | `"main"` | Branch to use when `repo_url` is overridden. |
| `exclude_root_readme` | `false` | Skip the repo root README when building context. |
| `supported_doc_exts` | `[".md", ".rst", ".txt"]` | File extensions included in the search. |

## Auto-respond to new issues

Run `/help_docs` automatically when someone opens an issue — ideal for OSS projects with extensive docs:

1. Set up MergeMate as a [GitHub Action](../installation/github.md#run-as-a-github-action).
2. Create `.github/workflows/help_docs.yml`:

```yaml
name: Auto-respond from docs
on:
  issues:
    types: [opened]

env:
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  GITHUB_API_URL: ${{ github.api_url }}
  ISSUE_URL: ${{ github.event.issue.html_url }}
  ISSUE_BODY: ${{ github.event.issue.body }}
  OPENAI_KEY: ${{ secrets.OPENAI_KEY }}

jobs:
  help_docs:
    runs-on: ubuntu-latest
    if: ${{ github.event.sender.type != 'Bot' }}
    permissions:
      contents: read
      issues: write
    steps:
      - name: Answer from docs
        uses: docker://mergemate/mergemate:latest
        with:
          entrypoint: /bin/bash
          args: |
            -c "cd /app && \
            export config__git_provider='github' && \
            export github__user_token=$GITHUB_TOKEN && \
            export github__base_url=$GITHUB_API_URL && \
            export openai__key=$OPENAI_KEY && \
            python -m mergemate.cli --issue_url=$ISSUE_URL help_docs \"$ISSUE_BODY\""
```

3. Commit and push to your default branch.

## Tips

- **Set `repo_url`** if your docs live in a central wiki repo separate from the code.
- **Exclude files** with `supported_doc_exts` if you have large non-text files in the docs folder.
- **Auto-respond mode** is a force multiplier for projects that get repetitive questions — point users at the right docs before a maintainer even sees the issue.
