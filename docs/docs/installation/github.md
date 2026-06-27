# GitHub Integration

Two paths to running MergeMate on GitHub: drop a workflow YAML into your repo for a zero-infrastructure setup, or deploy as a dedicated GitHub App when you need full control.

## Run as a GitHub Action

The simplest path. MergeMate ships as a pre-built action that slots right into your CI.

### One-Minute Setup

1. Create `.github/workflows/mergemate.yml` in your repo:

    ```yaml
    on:
      pull_request:
        types: [opened, reopened, ready_for_review]
      issue_comment:
    jobs:
      mergemate_job:
        if: ${{ github.event.sender.type != 'Bot' }}
        runs-on: ubuntu-latest
        permissions:
          issues: write
          pull-requests: write
          contents: write
        name: Run MergeMate on every PR, respond to comments
        steps:
          - name: MergeMate action step
            id: mergemate
            uses: mergemate/mergemate@main
            env:
              OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
              GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    ```

2. Add your OpenAI key as a repo secret (`Settings > Secrets and variables > Actions > New repository secret`):

    ```
    Name  = OPENAI_KEY
    Value = <your key>
    ```

    `GITHUB_TOKEN` is handled automatically by GitHub — you don't need to create it.

3. Merge to your main branch. The next time you open a PR, you'll see MergeMate's review appear as a comment, along with instructions for the rest of the tool suite.

4. Tweak behaviour by layering any [config option](https://github.com/imtiyaazsalie/mergemate/blob/main/mergemate/settings/configuration.toml) into the `env` block:

    ```yaml
          env:
            OPENAI.ORG: "<Your OpenAI org>"
            PR_REVIEWER.REQUIRE_TESTS_REVIEW: "false"
            PR_CODE_SUGGESTIONS.NUM_CODE_SUGGESTIONS: "6"
    ```

Dive deeper in the [usage guide](../usage-guide/automations_and_usage.md#github-action).

---

### Configuration Recipes

#### Choose Your Model

=== "OpenAI (default)"

    ```yaml
          env:
            OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
            GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            github_action_config.auto_review: "true"
            github_action_config.auto_describe: "true"
            github_action_config.auto_improve: "true"
    ```

=== "Gemini (Google AI Studio)"

    ```yaml
          env:
            GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            config.model: "gemini/gemini-1.5-flash"
            config.fallback_models: '["gemini/gemini-1.5-flash"]'
            GOOGLE_AI_STUDIO.GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
            github_action_config.auto_review: "true"
            github_action_config.auto_describe: "true"
            github_action_config.auto_improve: "true"
    ```

    **Secrets you'll need:** `GEMINI_API_KEY` (from [Google AI Studio](https://aistudio.google.com/)).
    No `OPENAI_KEY` required when using Gemini.

=== "Claude (Anthropic)"

    ```yaml
          env:
            GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            config.model: "anthropic/claude-3-opus-20240229"
            config.fallback_models: '["anthropic/claude-3-haiku-20240307"]'
            ANTHROPIC.KEY: ${{ secrets.ANTHROPIC_KEY }}
            github_action_config.auto_review: "true"
            github_action_config.auto_describe: "true"
            github_action_config.auto_improve: "true"
    ```

    **Secrets you'll need:** `ANTHROPIC_KEY` (from the [Anthropic Console](https://console.anthropic.com/)).

=== "Azure OpenAI"

    ```yaml
          env:
            OPENAI_KEY: ${{ secrets.AZURE_OPENAI_KEY }}
            GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            OPENAI.API_TYPE: "azure"
            OPENAI.API_VERSION: "2023-05-15"
            OPENAI.API_BASE: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
            OPENAI.DEPLOYMENT_ID: ${{ secrets.AZURE_OPENAI_DEPLOYMENT }}
            config.model: "gpt-4o"
            config.fallback_models: '["gpt-4o"]'
            github_action_config.auto_review: "true"
            github_action_config.auto_describe: "true"
            github_action_config.auto_improve: "true"
    ```

    **Secrets you'll need:** `AZURE_OPENAI_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`.

=== "Ollama (local models)"

    ```yaml
          env:
            OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
            GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            config.model: "ollama/qwen2.5-coder:32b"
            config.fallback_models: '["ollama/qwen2.5-coder:32b"]'
            config.custom_model_max_tokens: "128000"
            OLLAMA.API_BASE: "http://localhost:11434"
            github_action_config.auto_review: "true"
            github_action_config.auto_describe: "true"
            github_action_config.auto_improve: "true"
    ```

    You'll need a self-hosted runner with Ollama installed — hosted runners can't reach `localhost`.

=== "Amazon Bedrock"

    Static credentials:

    ```yaml
          env:
            GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            config.model: "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0"
            config.fallback_models: '["bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0"]'
            aws.AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
            aws.AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
            aws.AWS_REGION_NAME: "us-east-1"
    ```

    Running on EC2/ECS/EKS? Skip the secrets and lean on the instance role:

    ```yaml
          env:
            GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            config.model: "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0"
            config.fallback_models: '["bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0"]'
            AWS_USE_IMDS: "true"
    ```

    The IAM role needs `bedrock:InvokeModel` on the target model ARN. See the [Bedrock config guide](../usage-guide/changing_a_model.md#amazon-bedrock) for the full policy example.

---

#### Fine-Tune Behaviour

**Custom review instructions:**

```yaml
      env:
        OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        pr_reviewer.extra_instructions: "Focus on security vulnerabilities and performance. Check error handling patterns."
        github_action_config.auto_review: "true"
        github_action_config.auto_describe: "true"
        github_action_config.auto_improve: "true"
```

**Language-specific tuning:**

```yaml
      env:
        OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        pr_reviewer.extra_instructions: "Emphasise Python best practices, type hints, and docstrings."
        pr_code_suggestions.num_code_suggestions: "8"
        pr_code_suggestions.suggestions_score_threshold: "7"
        github_action_config.auto_review: "true"
        github_action_config.auto_describe: "true"
        github_action_config.auto_improve: "true"
```

**Pick which tools fire automatically:**

```yaml
      env:
        OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        github_action_config.auto_review: "true"
        github_action_config.auto_describe: "true"
        github_action_config.auto_improve: "false"
        github_action_config.pr_actions: '["opened", "reopened"]'
```

---

#### Drive Everything via `.mergemate.toml`

Dropping a config file in your repo root keeps the workflow YAML clean:

`.mergemate.toml`:
```toml
[config]
model = "gemini/gemini-1.5-flash"
fallback_models = ["anthropic/claude-3-opus-20240229"]

[pr_reviewer]
extra_instructions = "Focus on security and code quality."

[pr_code_suggestions]
num_code_suggestions = 6
suggestions_score_threshold = 7
```

Paired with a lean workflow:

```yaml
on:
  pull_request:
    types: [opened, reopened, ready_for_review]
  issue_comment:
jobs:
  mergemate_job:
    if: ${{ github.event.sender.type != 'Bot' }}
    runs-on: ubuntu-latest
    permissions:
      issues: write
      pull-requests: write
      contents: write
    name: MergeMate — auto review on PR, respond to comments
    steps:
      - name: MergeMate action step
        id: mergemate
        uses: mergemate/mergemate@main
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GOOGLE_AI_STUDIO.GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          ANTHROPIC.KEY: ${{ secrets.ANTHROPIC_KEY }}
          github_action_config.auto_review: "true"
          github_action_config.auto_describe: "true"
          github_action_config.auto_improve: "true"
```

---

#### Troubleshooting

**"Model not found"**
Double-check the model identifier format (e.g. `gemini/gemini-1.5-flash`, not bare `gemini-1.5-flash`). Verify the key is set as a repo secret and that your account has access to the model.

**"API key not found"**
Confirm the secret name matches *exactly* what the workflow expects. When using Gemini, Claude, or Bedrock, you only need the provider-specific key — `OPENAI_KEY` is not required.

**"Rate limit exceeded"**
Add fallback models or bump the timeout:

```yaml
      env:
        OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        config.fallback_models: '["gpt-4o-mini"]'
        config.ai_timeout: "300"
        github_action_config.auto_review: "true"
        github_action_config.auto_describe: "true"
        github_action_config.auto_improve: "true"
```

**"Permission denied"**
Make sure the workflow permissions block includes `issues: write`, `pull-requests: write`, and `contents: write`.

**"Invalid JSON format"**
Arrays in env vars must be JSON-encoded strings:

```yaml
# Correct
config.fallback_models: '["model1", "model2"]'

# Wrong — YAML interprets this as a list
config.fallback_models: ["model1", "model2"]
```

**Debugging tips:**
- Set `config.verbosity_level: "2"` for detailed logs.
- Inspect the Actions run output for specific error messages.
- Start with a minimal config and layer options on one at a time.
- Triple-check that secrets exist under your repo's Actions settings.

**Performance for large repos:**

```yaml
      env:
        OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        config.large_patch_policy: "clip"
        config.max_model_tokens: "32000"
        config.patch_extra_lines_before: "3"
        config.patch_extra_lines_after: "1"
        github_action_config.auto_review: "true"
        github_action_config.auto_describe: "true"
        github_action_config.auto_improve: "true"
```

---

#### Pinning to a Release

Floating on `@main` is great for staying current, but pin to a tagged release when you want stability:

```yaml
steps:
  - name: MergeMate action step
    id: mergemate
    uses: docker://mergemate/mergemate:0.34.2-github_action
```

For airtight reproducibility, pin by digest:

```yaml
steps:
  - name: MergeMate action step
    id: mergemate
    uses: docker://mergemate/mergemate@sha256:a0b36966ca3a197ca739fa1e65c16703076fc1c744cd423ca203b8c21707d71c
```

Official images ship with GitHub Artifact Attestations, so you can verify a digest came from this repo:

```sh
gh attestation verify \
  "oci://index.docker.io/mergemate/mergemate@sha256:<digest>" \
  --repo The-MergeMate/mergemate
```

#### GitHub Enterprise Server

Point MergeMate at your on-prem instance by setting the base URL:

```yaml
      env:
        GITHUB__BASE_URL: "https://github.mycompany.com/api/v3"
```

---

## Run as a GitHub App

Prefer a standalone deployment? The GitHub App path gives you full control over the runtime environment.

1. Create a GitHub App from the [developer portal](https://docs.github.com/en/apps/creating-github-apps).

    Permissions to set:
    - Pull requests — Read & write
    - Issue comment — Read & write
    - Metadata — Read-only
    - Contents — Read-only

    Events to subscribe to:
    - Issue comment
    - Pull request
    - Push (needed if you want reviews to fire on PR updates)

2. Generate a webhook secret:

    ```bash
    WEBHOOK_SECRET=$(python -c "import secrets; print(secrets.token_hex(10))")
    ```

3. From your app's settings page, note down:
    - App private key (generate one and save the `.pem` file)
    - App ID

4. Clone MergeMate:

    ```bash
    git clone https://github.com/imtiyaazsalie/mergemate.git
    ```

5. Copy the secrets template and fill in your values:

    ```bash
    cp mergemate/settings/.secrets_template.toml mergemate/settings/.secrets.toml
    ```

    Populate:
    - Your model provider key
    - `private_key` — paste the contents of your `.pem` file
    - `app_id` — your app's numeric ID
    - `webhook_secret` — the secret from step 2
    - Set `deployment_type = "app"` in your configuration.

    > The `.secrets.toml` file is excluded from Docker builds by default. For production, inject secrets as environment variables or mount them as a volume. In Kubernetes, for example:
    >
    > ```yaml
    > volumes:
    >   - name: settings-volume
    >     secret:
    >       secretName: mergemate-settings
    > containers:
    >   - volumeMounts:
    >       - mountPath: /app/mergemate/settings_prod
    >         name: settings-volume
    > ```

6. Build and push the Docker image:

    ```bash
    docker build . -t mergemate/mergemate:github_app --target github_app -f docker/Dockerfile
    docker push mergemate/mergemate:github_app
    ```

7. Deploy the image wherever suits you — a server, a serverless function, a container cluster. For local dev and debugging, [smee.io](https://smee.io) is handy for forwarding webhooks to your machine. You can also [deploy as a Lambda](#deploy-as-a-lambda-function).

8. Back in your app's settings, configure:
    - **Webhook URL** — your app's public endpoint (or smee.io channel URL)
    - **Webhook secret** — the secret from step 2

9. Install the app on your desired repositories from the "Install App" tab.

    > When running as a GitHub App, MergeMate loads its default config from `configuration.toml`. Override tool parameters per-repo by placing a `.mergemate.toml` file in the repository root. See the [usage guide](../usage-guide/automations_and_usage.md#github-app) for details.

---

## Additional Deployment Paths

### Deploy as a Lambda Function

AWS Lambda environment variables can't contain dots — replace each `.` with `__`. For example, `GITHUB.WEBHOOK_SECRET` becomes `GITHUB__WEBHOOK_SECRET`.

1. Follow steps 1–5 from the [GitHub App](#run-as-a-github-app) section above.
2. Build a Lambda-compatible image:

    ```shell
    docker buildx build --platform=linux/amd64 . \
      -t mergemate/mergemate:github_lambda \
      --target github_lambda \
      -f docker/Dockerfile.lambda
    ```

3. Push to ECR:

    ```shell
    docker tag mergemate/mergemate:github_lambda \
      <AWS_ACCOUNT>.dkr.ecr.<AWS_REGION>.amazonaws.com/mergemate/mergemate:github_lambda
    docker push <AWS_ACCOUNT>.dkr.ecr.<AWS_REGION>.amazonaws.com/mergemate/mergemate:github_lambda
    ```

4. Create a Lambda function using the uploaded image. Set the timeout to at least 3 minutes.
5. Give the Lambda a Function URL.
6. Set `AZURE_DEVOPS_CACHE_DIR` to a writable location like `/tmp` in the Lambda's environment variables.
7. Wire the Function URL as your GitHub App's webhook URL. It'll look like `https://<LAMBDA_FUNCTION_URL>/api/v1/github_webhooks`.

#### Using AWS Secrets Manager

For production Lambdas, prefer Secrets Manager over plain env vars:

1. Create a secret with your config in JSON:

    ```json
    {
      "openai.key": "sk-proj-...",
      "github.webhook_secret": "your-webhook-secret-from-step-2",
      "github.private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    }
    ```

2. Grant `secretsmanager:GetSecretValue` to your Lambda's execution role.
3. Set these env vars on the Lambda:

    ```bash
    AWS_SECRETS_MANAGER__SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:mergemate-secrets-AbCdEf
    CONFIG__SECRET_PROVIDER=aws_secrets_manager
    ```

---

### AWS CodeCommit

CodeCommit support is CLI-only for now (more features are on the roadmap). Here's how to review a CodeCommit PR from the command line:

1. Create an IAM user with programmatic access only (no console).
2. Attach IAM permissions for CodeCommit read access and comment posting. A working example:

    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "codecommit:BatchDescribe*",
                    "codecommit:BatchGet*",
                    "codecommit:Describe*",
                    "codecommit:EvaluatePullRequestApprovalRules",
                    "codecommit:Get*",
                    "codecommit:List*",
                    "codecommit:PostComment*",
                    "codecommit:PutCommentReaction",
                    "codecommit:UpdatePullRequestDescription",
                    "codecommit:UpdatePullRequestTitle"
                ],
                "Resource": "*"
            }
        ]
    }
    ```

    Tighten `Resource` to your specific repository ARNs in production.

3. Generate an Access Key for the IAM user.
4. Export the credentials:

    ```sh
    export AWS_ACCESS_KEY_ID="XXXXXXXXXXXXXXXX"
    export AWS_SECRET_ACCESS_KEY="XXXXXXXXXXXXXXXX"
    export AWS_DEFAULT_REGION="us-east-1"
    ```

5. Set `git_provider = "codecommit"` in your MergeMate config.
6. Make sure MergeMate is on your `PYTHONPATH`, then run:

    ```sh
    PYTHONPATH="/path/to/mergemate" python mergemate/cli.py \
      --pr_url https://us-east-1.console.aws.amazon.com/codesuite/codecommit/repositories/MY_REPO/pull-requests/321 \
      review
    ```
