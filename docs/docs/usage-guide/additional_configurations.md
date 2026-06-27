# Advanced configuration

---

## Seeing what's configured

All available settings live in the [config reference](https://github.com/mergemate/mergemate/blob/main/mergemate/settings/configuration.toml). Per-tool options are documented on each [tool's page](../tools/index.md).

To print the current config as a PR comment:

```
/config
```

![Config output](https://mergemate.ai/images/mergemate/possible_config1.png){width=512}

To see the *actual* resolved config for a specific tool (after all overrides are applied):

```
/improve --config.output_relevant_configurations=true
```

![Resolved config](https://mergemate.ai/images/mergemate/possible_config2.png){width=512}

---

## Ignoring files

Skip generated code, vendored dependencies, or anything else you don't want reviewed.

### Glob patterns

```
/review --ignore.glob="['*.py']"
```

Or in config:

```toml
[ignore]
glob = ['*.py']
```

### Regex patterns

```toml
[ignore]
regex = ['.*\\.py$']
```

---

## Extra instructions

Every tool accepts free-text guidance via `extra_instructions`:

```
/update_changelog --pr_update_changelog.extra_instructions="Also bump the version number"
```

---

## Response language

MergeMate defaults to U.S. English. To switch:

```toml
[config]
response_language = "ja-JP"
```

Uses [ISO 639](https://en.wikipedia.org/wiki/ISO_639) / [ISO 3166](https://en.wikipedia.org/wiki/ISO_3166) locale codes. [Full locale list →](https://simplelocalize.io/data/locales/)

Only AI-generated text is translated. Static labels and table headers stay in English. Make sure your model supports the target language well.

---

## GitLab submodule diffs

By default, GitLab shows submodule changes as a single `Subproject commit` line. To expand those into full diffs:

```toml
[gitlab]
expand_submodule_diffs = true
```

This adds extra API calls, so it's off by default.

---

## Log level

Control verbosity for debugging:

```toml
[config]
log_level = "DEBUG"  # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

Default is `DEBUG`.

---

## Observability platforms

MergeMate uses LiteLLM under the hood, so any LiteLLM-compatible observability tool works. Example with LangSmith:

```toml
[litellm]
enable_callbacks = true
success_callback = ["langsmith"]
failure_callback = ["langsmith"]
```

```bash
LANGSMITH_API_KEY=<key>
LANGSMITH_PROJECT=<project>
LANGSMITH_BASE_URL=<url>
```

---

## Repository metadata

Let MergeMate discover project-wide context automatically:

```toml
[config]
add_repo_metadata = true
```

It scans the PR's head branch for `AGENTS.MD`, `CLAUDE.MD`, and other metadata files.

Custom file list:

```toml
[config]
add_repo_metadata_file_list = ["CONTRIBUTING.md", "ARCHITECTURE.md"]
```

---

## Ignoring PRs automatically

### By title

```toml
[config]
ignore_pr_title = ["\\[Bump\\]"]
```

Regex patterns. Default: `["^\\[Auto\\]", "^Auto"]`.

### By branch

```toml
[config]
ignore_pr_source_branches = ['develop', 'main', 'master', 'stage']
ignore_pr_target_branches = ["qa"]
```

### By repository

```toml
[config]
ignore_repositories = ["my-org/my-repo1", "my-org/my-repo2"]
```

### By folder (monorepo allowlist)

```toml
[config]
allow_only_specific_folders = ['services/api', 'packages/core']
```

Only PRs touching files in these folders get automatic feedback.

### By label

```toml
[config]
ignore_pr_labels = ["do-not-merge"]
```

### By author

MergeMate auto-detects bots using GitHub's bot flag and common naming patterns. To add manual overrides:

```toml
[config]
ignore_pr_authors = ["my-bot-user", "dependabot"]
```

Regex list. Note: bots that create PRs with *failing tests* will still get a response.

### By generated file type

```toml
[config]
ignore_language_framework = ['protobuf']
```

Patterns come from [`generated_code_ignore.toml`](https://github.com/mergemate/mergemate/blob/main/mergemate/settings/generated_code_ignore.toml).

### By ticket label

When MergeMate pulls ticket context (JIRA, GitHub Issues, etc.), skip tickets with certain labels:

```toml
[config]
ignore_ticket_labels = ["ignore-compliance", "skip-review", "wont-fix"]
```
