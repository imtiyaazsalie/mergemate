# Update Changelog

**Writes a changelog entry from the PR diff — either as a comment for review, or committed straight to `CHANGELOG.md`.**

```
/update_changelog
```

By default, the tool publishes the proposed entry as a PR comment. Turn on `push_changelog_changes` and it commits directly.

![update_changelog](https://mergemate.ai/images/mergemate/update_changelog.png){width=768}

## Configuration

(`[pr_update_changelog]` section)

| Option | Default | Notes |
|---|---|---|
| `push_changelog_changes` | `false` | When `true`, commits the entry to `CHANGELOG.md`. When `false`, posts it as a comment. |
| `extra_instructions` | `""` | Guidance for the model, e.g. "group entries under Added / Changed / Fixed headings." |
| `add_pr_link` | `true` | Includes a link back to the PR in the changelog entry. |
| `skip_ci_on_push` | `true` | Adds `[skip ci]` to the commit message so CI doesn't trigger on changelog commits. |

**Example config:**

```toml
[pr_update_changelog]
push_changelog_changes = true
extra_instructions = "Use the Keep a Changelog format with Added, Changed, Deprecated, Removed, Fixed, Security sections."
```

## Tips

- **Preview first.** Keep `push_changelog_changes = false` until you trust the output, then switch it on.
- **Use `skip_ci_on_push`** to avoid triggering a full pipeline for a changelog-only commit.
- **Pair with `/describe`** — run `/describe` to get the PR type and summary, then `/update_changelog` to persist it.
- **Extra instructions shape the format.** Tell the model exactly which sections you use and it'll follow suit.
