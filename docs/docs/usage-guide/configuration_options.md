# Configuration

MergeMate reads its settings from a TOML file. You can place it in four locations, ranked by priority:

| Layer | Scope | Overrides |
|---|---|---|
| 1. **Wiki** | Single repo (GitHub, GitLab, Bitbucket) | Everything below |
| 2. **Local** (`.mergemate.toml` in repo root) | Single repo | Global + external |
| 3. **Global** (`mergemate-settings` repo) | Entire org / project / group | External URL |
| 4. **External URL** (CLI flag) | Any | Nothing (applied first) |

---

!!! tip "Keep it minimal"
    Only set the values you need to change. Copying the full defaults file creates maintenance headaches later.

!!! tip "Debug your config"
    Set `config.output_relevant_configurations = true` to see exactly which settings each tool is using — printed in a collapsible section in the output.

---

## Wiki config

Create a wiki page called `.mergemate.toml` in your repo. No commits needed — just edit and save.

Wrap your config in triple backticks for clean rendering:

~~~toml
```toml
[pr_description]
generate_ai_title = true
```
~~~

MergeMate strips the markdown wrapper automatically.

![Wiki config example](https://mergemate.ai/images/mergemate/wiki_configuration.png){width=512}

---

## Local config

Drop a `.mergemate.toml` file in the root of your repo's default branch. Upload it *before* running tools for the config to take effect.

```toml
[pr_reviewer]
extra_instructions = """\
- Check for SQL injection
- Verify error handling
"""
```

### Loading from a non-default branch

`Platform: GitHub`

By default, MergeMate reads `.mergemate.toml` from the default branch. Point it elsewhere with:

```bash
python -m mergemate.cli \
  --pr_url=<URL> \
  --config-branch=<branch-name> \
  review
```

Or set `MERGEMATE_CONFIG_BRANCH`. The CLI flag wins. If the file isn't found on the requested branch, MergeMate logs a warning and falls back to default.

!!! danger "Security: config branch is a trust boundary"
    By default, only people who can merge to the default branch control MergeMate's behavior. `--config-branch` moves that trust boundary.

    **Never** set it from untrusted input like `$GITHUB_HEAD_REF`. An attacker could supply their own `.mergemate.toml` and redirect model calls, inject instructions, or enable auto-approval. Always pin it to a maintainer-controlled branch.

!!! note "GitHub only"
    Branch selection is currently GitHub-only. Other platforms ignore the flag and always read from the default branch.

---

## Global config

Create a repo called `mergemate-settings` in your org. Every repo in that org inherits its `.mergemate.toml`.

Local `.mergemate.toml` files override it per-repo.

**Example:** `https://github.com/mergemate-ai/mergemate-settings` serves as the global config for all repos under the `mergemate-ai` org.

---

## Project / Group config

`Platforms: GitLab, Bitbucket Data Center`

Create a `mergemate-settings` repo inside a GitLab group/subgroup or Bitbucket project. It applies to all repos directly under that group/project.

!!! note ""
    For GitLab, if a repo is nested under multiple subgroups, MergeMate only looks one level up.

---

## Organization-level config

`Platform: Bitbucket Data Center`

Create a project named `MERGEMATE_SETTINGS` (key: `MERGEMATE_SETTINGS`), add a `mergemate-settings` repo, and put your `.mergemate.toml` inside. Every repo across every project inherits it.

Project-level settings override organization-level. Repo-local `.mergemate.toml` beats both.

---

## External config URL

`Platforms: all`

Pass an additional config file from any URL or local path. Applied *before* all other layers — it acts as a base default.

```bash
python -m mergemate.cli \
  --pr_url=<URL> \
  --extra_config_url=https://config.example.com/shared.toml \
  review
```

Accepted schemes: `https://`, `http://`, `file://`, or a bare path.

### Private endpoints

Supply an auth header:

```bash
export MERGEMATE_EXTRA_CONFIG_AUTH_HEADER="PRIVATE-TOKEN: <your-token>"
export MERGEMATE_EXTRA_CONFIG_AUTH_HEADER="Authorization: Bearer <your-token>"
```

### Full precedence chain

```
built-in defaults
  ← --extra_config_url
    ← global mergemate-settings
      ← local .mergemate.toml (repo default branch)
        ← wiki .mergemate.toml
          ← environment variables (MERGEMATE__SECTION__KEY)
```

### Security limits

- Max response size: **1 MB**
- Request timeout: **10 seconds**
- Only `http`, `https`, `file` schemes accepted
- No executable directives (includes, custom loaders)

If the fetch fails, MergeMate logs it and moves on.
