# Running MergeMate on Your Machine

## AI-Powered Setup

The fastest way to get started — MergeMate auto-detects your project and generates everything:

```bash
pip install mergemate-review
mergemate-review init
```

It detects your language, git provider, and project type, then uses AI to generate the optimal `.mergemate.toml` and GitHub Actions workflow. You get a production-ready setup in under 30 seconds.

```bash
# Point it at an existing repo
mergemate-review init --output /path/to/repo

# Specify your preferences
mergemate-review init --model deepseek/deepseek-v4-flash --language python --project-type web
```

---

## Manual Setup

Before you start, you'll need two things:

1. **A model provider key** — grab one from [OpenAI](https://platform.openai.com/api-keys){:target="_blank"} (GPT-4o or later), or configure MergeMate to use any of the [supported models](../usage-guide/changing_a_model.md).
2. **A git platform token** — generate a personal access token with repo scope from your provider. For GitHub, head to [developer settings](https://github.com/settings/tokens){:target="_blank"}. GitLab, Bitbucket, and Gitea all have equivalent token flows.

## Quick Start with Docker

The fastest way to try MergeMate. Pick your git provider and run:

=== "GitHub"

    ```bash
    docker run --rm -it \
      -e OPENAI__KEY=<your_key> \
      -e GITHUB__USER_TOKEN=<your_github_token> \
      imtiyaazsalie/mergemate-review:latest \
      --pr_url <pr_url> review
    ```

    If you're on GitHub Enterprise Server, point MergeMate at your instance:

    ```bash
    -e GITHUB__BASE_URL=https://github.mycompany.com/api/v3
    ```

=== "GitLab"

    ```bash
    docker run --rm -it \
      -e OPENAI__KEY=<your_key> \
      -e CONFIG__GIT_PROVIDER=gitlab \
      -e GITLAB__PERSONAL_ACCESS_TOKEN=<your_token> \
      imtiyaazsalie/mergemate-review:latest \
      --pr_url <pr_url> review
    ```

    Self-hosted GitLab? Add your instance URL:

    ```bash
    -e GITLAB__URL=https://gitlab.mycompany.com
    ```

=== "Bitbucket"

    ```bash
    docker run --rm -it \
      -e CONFIG__GIT_PROVIDER=bitbucket \
      -e OPENAI__KEY=$OPENAI_API_KEY \
      -e BITBUCKET__BEARER_TOKEN=$BITBUCKET_BEARER_TOKEN \
      imtiyaazsalie/mergemate-review:latest \
      --pr_url=<pr_url> review
    ```

=== "Gitea"

    ```bash
    docker run --rm -it \
      -e OPENAI__KEY=<your_key> \
      -e CONFIG__GIT_PROVIDER=gitea \
      -e GITEA__PERSONAL_ACCESS_TOKEN=<your_token> \
      imtiyaazsalie/mergemate-review:latest \
      --pr_url <pr_url> review
    ```

    For a self-hosted Gitea instance:

    ```bash
    -e GITEA__URL=https://gitea.mycompany.com
    ```

For any other git platform, adjust `CONFIG__GIT_PROVIDER` and check the [secrets template](https://github.com/imtiyaazsalie/mergemate/blob/main/mergemate/settings/.secrets_template.toml) for the correct environment variable names.

### Driving Configuration Through Environment Variables

Every setting in MergeMate can be overridden with an environment variable. The convention is simple: `<SECTION>__<KEY>=<VALUE>`. In other words, a dot or double-underscore separates the config section from the key.

Say you're connecting to a self-hosted GitLab instance. Drop these into a `.env` file:

```bash
CONFIG__GIT_PROVIDER="gitlab"
GITLAB__URL="https://gitlab.mycompany.com"
GITLAB__PERSONAL_ACCESS_TOKEN="<your token>"
OPENAI__KEY="<your key>"
```

Then fire it up:

```shell
docker run --rm -it --env-file .env imtiyaazsalie/mergemate-review:latest review <pr_url>
```

---

### Troubles? Check Your Keys

Docker errors almost always come down to a misconfigured API key or access token. LiteLLM (the model gateway MergeMate uses under the hood) sometimes surfaces opaque messages like `APIError: OpenAIException - Connection error.` — don't trust the surface-level error; double-check your credentials first.

If you're using Azure OpenAI, there are extra fields you need to set. Same goes for Anthropic, Gemini, or any other provider. Flip over to the [model configuration guide](../usage-guide/changing_a_model.md) for the exact keys each provider expects.

## Installing with pip

```bash
pip install mergemate-review
```

Then drive it from Python:

```python
from mergemate import cli
from mergemate.config_loader import get_settings

def main():
    # Fill these in
    provider = "github"  # github | gitlab | bitbucket | azure_devops
    user_token = "..."   # your git platform token
    openai_key = "..."   # your model provider key
    pr_url = "..."       # e.g. https://github.com/imtiyaazsalie/mergemate/pull/809
    command = "/review"  # /review, /describe, /ask="...", /improve, etc.

    # Wire up config
    get_settings().set("CONFIG.git_provider", provider)
    get_settings().set("openai.key", openai_key)
    get_settings().set("github.user_token", user_token)

    # Go
    cli.run_command(pr_url, command)

if __name__ == "__main__":
    main()
```

Results land directly as comments on the PR.

## Running from Source

1. Grab the repo:

    ```bash
    git clone https://github.com/imtiyaazsalie/mergemate.git
    ```

2. Hop into the `mergemate` directory and install (a virtual environment is strongly recommended):

    ```bash
    pip install -e .
    ```

    *Hit a Rust-related error? Make sure Rust is installed and on your `PATH`: [https://rustup.rs](https://rustup.rs)*

3. Copy the secrets template and populate it with your keys:

    ```bash
    cp mergemate/settings/.secrets_template.toml mergemate/settings/.secrets.toml
    chmod 600 mergemate/settings/.secrets.toml
    # Open .secrets.toml in your editor and fill in the values
    ```

4. Start using the CLI:

    ```bash
    python3 -m mergemate.cli --pr_url <pr_url> review
    python3 -m mergemate.cli --pr_url <pr_url> describe
    python3 -m mergemate.cli --pr_url <pr_url> improve
    python3 -m mergemate.cli --pr_url <pr_url> ask "what does this PR do?"
    python3 -m mergemate.cli --pr_url <pr_url> add_docs
    python3 -m mergemate.cli --pr_url <pr_url> generate_labels
    python3 -m mergemate.cli --issue_url <issue_url> similar_issue
    ```

    Optionally toss MergeMate onto your `PYTHONPATH`:

    ```bash
    export PYTHONPATH=$PYTHONPATH:<path to mergemate directory>
    ```
