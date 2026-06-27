# Review

**Generates structured, configurable feedback on a pull request to accelerate reviews.**

Trigger it from the command line or by commenting on a PR.

```
mergemate-review --pr_url https://github.com/owner/repo/pull/42 review
```

When you're already in a PR thread, just drop:

```
/review
```

MergeMate responds in ~30 seconds with a breakdown of findings, security concerns, review effort, and any sections you've enabled.


To tweak behaviour on the fly, append config overrides:

```
/review --pr_reviewer.extra_instructions="focus on auth logic" --pr_reviewer.num_max_findings=5
```

## Automating review

Add `/review` to your `pr_commands` list and it fires every time a PR opens:

```toml
[github_app]
pr_commands = [
    "/review",
]

[pr_reviewer]
extra_instructions = "Flag any hardcoded credentials."
```

## Configuration

### General

| Option | Default | Notes |
|---|---|---|
| `persistent_comment` | `true` | Edits the same comment on re-runs instead of creating new ones. |
| `final_update_message` | `true` | Posts a short notice linking to the updated review. |
| `extra_instructions` | `""` | Guidance for the AI, e.g. "ignore .md files, focus on concurrency." |
| `enable_help_text` | `false` | Appends help text to the review comment. |
| `num_max_findings` | `3` | Caps the number of findings returned. |

### Review sections — toggle what appears

| Option | Default | What it controls |
|---|---|---|
| `require_score_review` | `false` | Scores the PR numerically. |
| `require_tests_review` | `true` | Checks whether tests accompany the changes. |
| `require_estimate_effort_to_review` | `true` | Estimates reviewer effort on a 1–5 scale. |
| `require_estimate_contribution_time_cost` | `false` | Estimates how long a senior dev would need to author the same changes. |
| `require_can_be_split_review` | `false` | Flags PRs that could be split into smaller units. |
| `require_security_review` | `true` | Scans for potential security issues. |
| `require_todo_scan` | `false` | Lists leftover `TODO` comments in the diff. |
| `require_ticket_analysis_review` | `true` | Checks if linked tickets are actually fulfilled by the PR. |

### Auto-labeling

| Option | Default | Notes |
|---|---|---|
| `enable_review_labels_security` | `true` | Applies a `possible security issue` label when the tool flags a risk. |
| `enable_review_labels_effort` | `true` | Applies a `Review effort x/5` label. |

## Tips

- **Start with defaults, then tune.** Enable `require_score_review` and `require_can_be_split_review` if your team values those signals.
- **Extra instructions are your superpower.** Tell the model exactly what your team cares about. Use triple-quoted strings for multi-line guidance.
- **Use labels as guardrails.** CI can block merges based on labels like `possible security issue`. Remove a label deliberately if it's a false positive — MergeMate logs the override.
- **Review in context.** If you ask for ticket analysis, include a GitHub or Jira link in the PR description so the tool can cross-reference.
