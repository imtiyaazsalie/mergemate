# Generate Labels

**Assigns labels to a pull request based on the content and intent of the code changes.**

```
/generate_labels
```

Runs a focused analysis of the diff and attaches relevant labels. Unlike `/describe`, this tool does nothing but labels — no title, no summary, no walkthrough.


## `/generate_labels` vs `/describe` labels

| | `/generate_labels` | `/describe` |
|---|---|---|
| Output | Labels only | Full PR description + labels |
| Speed | Faster — single-purpose | Covers more ground |
| Use when | You just want labels | You want a complete PR write-up |

Both tools respect the same custom label definitions.

## Custom labels

Enable and define labels that match your team's workflow:

```toml
[config]
enable_custom_labels = true

[custom_labels."Bug fix"]
description = "A fix for a bug in production or pre-release code."

[custom_labels."Feature"]
description = "A new feature or user-facing enhancement."

[custom_labels."Documentation"]
description = "Changes that only touch docs, READMEs, or comments."

[custom_labels."Performance"]
description = "Changes that measurably affect runtime speed or memory."

[custom_labels."Refactoring"]
description = "Structural changes with no functional difference."
```

Each description is a prompt for the AI — write it as a conditional statement describing *when* the label fits.

### Managing labels from the repo

On GitHub, go to the **Labels** tab under Issues. Create a label with a description prefixed by `mergemate:`:

```
mergemate: Use when a new public API endpoint is introduced.
```

MergeMate will discover these labels and use them automatically.

## Tips

- **Define a small, precise set of labels.** Five to eight well-described labels work better than twenty vague ones.
- **Combine with automation.** Add `/generate_labels` to `pr_commands` so every new PR is labelled immediately.
- **Audit occasionally.** If the AI consistently mislabels certain PRs, tighten the label description or split the label into two.
