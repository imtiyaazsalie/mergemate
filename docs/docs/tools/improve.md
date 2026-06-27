# Improve

**Delivers concrete, actionable code suggestions — displayed as an interactive table or inline comments.**

From the CLI:

```
mergemate-review --pr_url https://github.com/owner/repo/pull/42 improve
```

In a PR thread:

```
/improve
```

By default, suggestions appear as a compact table. Click any row to expand the full diff. Switch to inline committable comments with a config toggle.


Override settings inline:

```
/improve --pr_code_suggestions.commitable_code_suggestions=true --pr_code_suggestions.num_code_suggestions_per_chunk=5
```

## Two display modes

| Mode | How to enable | Best for |
|---|---|---|
| **Table** (default) | Default; `commitable_code_suggestions = false` | Clean PRs, quick overview, prioritisation by score. |
| **Inline comments** | `commitable_code_suggestions = true` | Teams that want each suggestion on its own review thread. |

> Bitbucket Cloud and Server support inline mode only.

### Dual publishing

Set a score threshold to surface top suggestions as inline comments *in addition* to the table:

```toml
[pr_code_suggestions]
dual_publishing_score_threshold = 7
```

Suggestions scoring ≥ 7 appear in both places. Default is `-1` (off).

## Automating suggestions

```toml
[github_app]
pr_commands = [
    "/improve",
]

[pr_code_suggestions]
num_code_suggestions_per_chunk = 4
```

## Extra instructions & best practices

### Extra instructions

Fine-tune the model's output with `extra_instructions`:

```toml
[pr_code_suggestions]
extra_instructions = """\
- Prefer early returns over deep nesting.
- Never suggest adding `console.log` statements.
- Ignore changes in .yml and .toml files.
"""
```

### Best practices file

Drop a `best_practices.md` in your repo root. MergeMate reads it and flags violations with an `Organization best practice` label. Keep it under 800 lines and focus on project-specific rules the AI wouldn't already know.

**extra_instructions** controls *how* the tool behaves. **best_practices.md** defines *what good code looks like* in your repo. Use both.

## Self-review workflow

Prompt the PR author to confirm they've reviewed the suggestions:

```toml
[pr_code_suggestions]
demand_code_suggestions_self_review = true
code_suggestions_self_review_text = "I have reviewed all suggestions and applied the ones that make sense."
```

- `fold_suggestions_on_self_review` (default `true`) collapses the table after the checkbox is ticked — less visual noise for reviewers.
- `approve_pr_on_self_review` (default `false`) auto-approves when the author checks the box. Use with care: it requires a deliberate config-file commit to enable.

## How suggestions scale

MergeMate breaks PRs into chunks (up to 32k tokens each) and generates `num_code_suggestions_per_chunk` suggestions per chunk (default 3). Cap the number of chunks with `max_number_of_calls`. This keeps quality high even for large diffs.

## Configuration

### General

| Option | Default | Notes |
|---|---|---|
| `extra_instructions` | `""` | Additional guidance for the model. |
| `commitable_code_suggestions` | `false` | Switches to inline PR comments. |
| `dual_publishing_score_threshold` | `-1` | Score threshold for dual publishing (disabled by default). |
| `focus_only_on_problems` | `true` | Prioritises bugs and issues over style nits. |
| `persistent_comment` | `true` | Edits the same comment on re-runs. |
| `suggestions_score_threshold` | `0` | Drops suggestions below this importance score. Don't go above 7–8. |
| `enable_help_text` | `false` | Appends help text to the comment. |
| `enable_chat_text` | `false` | Adds a link to the PR chat. |
| `publish_output_no_suggestions` | `true` | Posts a comment even when zero suggestions are found. |

### AI call control

| Option | Default | Notes |
|---|---|---|
| `num_code_suggestions_per_chunk` | `3` | Suggestions per chunk. |
| `max_number_of_calls` | `3` | Max number of chunks to process. |

## Tips

- **Stick with table mode** unless you have a strong preference for inline comments. It's cleaner and easier to scan.
- **Set a score threshold** (`suggestions_score_threshold = 7`) to hide low-signal suggestions.
- **Combine extra_instructions and best_practices.md** for suggestions that genuinely match your team's standards.
- **Self-review + fold** reduces PR noise and shows reviewers the author has already engaged with the feedback.
- **Treat diffs as illustrative** — the description often matters more than the exact code snippet.
