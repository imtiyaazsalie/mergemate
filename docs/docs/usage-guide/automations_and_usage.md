# Running & automating MergeMate

## CLI

Fire off tools from your terminal. Your local config drives everything.

```bash
# Review a PR
python -m mergemate.cli --pr_url=https://github.com/owner/repo/pull/50 review

# Generate a description
python -m mergemate.cli --pr_url=https://github.com/owner/repo/pull/50 describe

# Suggest improvements
python -m mergemate.cli --pr_url=https://github.com/owner/repo/pull/50 improve

# Ask anything
python -m mergemate.cli --pr_url=https://github.com/owner/repo/pull/50 ask "Summarize the security impact of this PR"

# Update the changelog
python -m mergemate.cli --pr_url=https://github.com/owner/repo/pull/50 update_changelog
```

**Pro tips:**

Override any config value inline:

```bash
python -m mergemate.cli --pr_url=<url> review --pr_reviewer.extra_instructions="Focus on error handling"
```

Run locally without publishing (great for testing):

```toml
[config]
publish_output = false
verbosity_level = 2
```

**Git providers:** set the `git_provider` field to `github` (default), `gitlab`, `bitbucket`, `azure`, `codecommit`, `local`, or `gitea`.

### Health check

Confirm everything is wired up:

```bash
python -m tests.health_test.main
```

You'll need an LLM provider configured and a valid token set before running this.

---

## Online usage

Trigger MergeMate by commenting on a PR:

| Command | What it does |
|---|---|
| `/review` | Full code review |
| `/describe` | PR summary + labels |
| `/improve` | Code suggestions |
| `/ask "..."` | Ask a question about the PR |
| `/update_changelog` | Update the changelog |

Tweak config on the fly:

```
/review --pr_reviewer.extra_instructions="..." --pr_reviewer.require_score_review=false
```

Any setting from the [config file](https://github.com/mergemate/mergemate/blob/main/mergemate/settings/configuration.toml) can be overridden this way. Run `/config` to see what's available.

---

## Automatic feedback

### Kill switch

To silence all automatic feedback across every platform:

```toml
[config]
disable_auto_feedback = true
```

No tools will fire on PR open or push events.

### GitHub App

#### On new PRs

Define which tools run automatically when a PR opens:

```toml
[github_app]
pr_commands = [
    "/describe",
    "/review",
    "/improve",
]
```

This fires on open, reopen, and ready-for-review transitions.

**Draft PRs** are skipped by default. To include them:

```toml
[github_app]
feedback_on_draft_pr = true
```

**Customize tool params for auto-runs:**

```toml
[pr_description]
generate_ai_title = true
```

Or target specific automated runs:

```toml
[github_app]
pr_commands = [
    "/describe",
    "/review --pr_reviewer.extra_instructions='Focus on SQL injection patterns'",
    "/improve",
]
```

Configuration follows the same [precedence rules](./configuration_options.md) (wiki → local → global).

#### On new commits

Respond to pushes on open PRs:

```toml
[github_app]
handle_push_trigger = true
push_commands = [
    "/describe",
    "/review",
]
```

### GitHub Action

GitHub Actions use environment variables, not the app config:

```yaml
env:
  OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  github_action_config.auto_review: "true"
  github_action_config.auto_describe: "true"
  github_action_config.auto_improve: "true"
  github_action_config.pr_actions: '["opened", "reopened", "ready_for_review", "review_requested"]'
```

The three `auto_*` flags control what runs on PR open. Default: all three are on.

`pr_actions` sets which pull request events trigger the automation. Default: `["opened", "reopened", "ready_for_review", "review_requested"]`.

`github_action_config.enable_output` toggles the action's JSON output parameter (default `true`).

You can also drop a `.mergemate.toml` in your repo root for additional config, or set more env vars:

```yaml
pr_description.publish_labels: "false"
```

#### Enable PR comment triggers

Add `issue_comment` events to your workflow:

```yaml
on:
  issue_comment:
    types: [created, edited]
```

#### Quick model config for GitHub Actions

| Model | Key env vars |
|---|---|
| **OpenAI** | `config.model: "gpt-5.4"`, `OPENAI_KEY` |
| **Gemini** | `config.model: "gemini/gemini-1.5-flash"`, `GOOGLE_AI_STUDIO.GEMINI_API_KEY` |
| **Claude** | `config.model: "anthropic/claude-3-opus-20240229"`, `ANTHROPIC.KEY` |
| **Azure OpenAI** | `OPENAI.API_TYPE: "azure"`, `OPENAI.API_BASE`, `OPENAI.DEPLOYMENT_ID` |
| **Local (Ollama)** | `config.model: "ollama/model-name"`, `OLLAMA.API_BASE` |

Environment variable format: use dots for nesting (`config.model`), strings for booleans (`"true"`), and JSON strings for arrays (`'["a", "b"]'`).

Full model setup guide: [Changing a model →](changing_a_model.md)

### GitLab Webhook

Same pattern as GitHub App:

```toml
[gitlab]
pr_commands = [
    "/describe",
    "/review",
    "/improve",
]
```

Push-trigger support:

```toml
[gitlab]
handle_push_trigger = true
push_commands = [
    "/describe",
    "/review",
]
```

Make sure your webhook has "Push events" scope enabled for `handle_push_trigger`.

### Bitbucket App

Bitbucket loads config from a `.mergemate.toml` file at the root of your repo's default branch. Upload it *before* creating PRs.

Example local overrides:

```toml
[pr_reviewer]
extra_instructions = "Answer in Japanese"
```

**Rate limit note:** Bitbucket caps app requests at ~1000/hour with no usage API. If you get spotty responses, try:

```toml
bitbucket_app.avoid_full_files = true
```

This skips full-file fetches (slight accuracy trade-off, fewer API calls).

#### Auto-run on PR open

```toml
[bitbucket_app]
pr_commands = [
    "/review",
    "/improve --pr_code_suggestions.commitable_code_suggestions=true --pr_code_suggestions.suggestions_score_threshold=7",
]
```

We recommend `suggestions_score_threshold=7` for Bitbucket since it only supports inline suggestions — fewer, higher-quality hits.

Push-trigger:

```toml
[bitbucket_app]
handle_push_trigger = true
push_commands = [
    "/describe",
    "/review",
]
```

### Azure DevOps

Set the provider and auth in config:

```toml
[config]
git_provider = "azure"
```

Two auth options:

- **PAT token** — quicker setup, inherits your user identity, expires by design
- **DefaultAzureCredential** — managed identity or service principal, more secure, separate identity

Secrets go in `.secrets.toml`:

```toml
[azure_devops]
org = "https://dev.azure.com/YOUR_ORGANIZATION/"
# pat = "YOUR_PAT_TOKEN"  # only if using PAT auth
```

For DefaultAzureCredential, set `AZURE_CLIENT_SECRET` (or use managed identity / `az login` locally).

#### Webhook auto-run

```toml
[azure_devops_server]
pr_commands = [
    "/describe",
    "/review",
    "/improve",
]
```

### Gitea Webhook

```toml
[gitea]
pr_commands = [
    "/describe",
    "/review",
    "/improve",
]
```
