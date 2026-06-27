# GitLab Integration

## Run as a GitLab CI Pipeline

The simplest route — MergeMate runs inside your existing GitLab CI without any extra infrastructure.

1. Add this to your repo's `.gitlab-ci.yml`:

    ```yaml
    stages:
      - mergemate

    mergemate_job:
      stage: mergemate
      image:
        name: mergemate/mergemate:latest
        entrypoint: [""]
      script:
        - cd /app
        - echo "Running MergeMate"
        - export MR_URL="$CI_MERGE_REQUEST_PROJECT_URL/merge_requests/$CI_MERGE_REQUEST_IID"
        - echo "MR_URL=$MR_URL"
        - export gitlab__url=$CI_SERVER_PROTOCOL://$CI_SERVER_FQDN
        - export gitlab__PERSONAL_ACCESS_TOKEN=$GITLAB_PERSONAL_ACCESS_TOKEN
        - export config__git_provider="gitlab"
        - export openai__key=$OPENAI_KEY
        - mergemate-review --pr_url="$MR_URL" describe
        - mergemate-review --pr_url="$MR_URL" review
        - mergemate-review --pr_url="$MR_URL" improve
      rules:
        - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    ```

    This fires on every new merge request. Tweak the `rules` block to target different events, and adjust the `script` section to run a different set of commands or pass custom env vars.

2. In your GitLab repo, go to **Settings > CI/CD > Variables** and add these masked variables:

    - `GITLAB_PERSONAL_ACCESS_TOKEN` — a token with API access
    - `OPENAI_KEY` — your model provider key

    If your base branches aren't protected, don't mark the variables as protected — otherwise the pipeline won't be able to read them.

    !!! note "`$CI_SERVER_FQDN` availability"
        The `$CI_SERVER_FQDN` variable was introduced in GitLab 16.10. On older versions, combine `$CI_SERVER_HOST` and `$CI_SERVER_PORT` to build the equivalent URL.

    !!! note "SSL verification"
        Use `gitlab__SSL_VERIFY` to point at a custom CA bundle. GitLab exposes `$CI_SERVER_TLS_CA_FILE` for this purpose. You can also disable verification entirely with `gitlab__SSL_VERIFY=false`, though that's not recommended in production.

---

## Run as a Webhook Server

For a self-hosted setup that responds to webhook events:

1. In GitLab, create a dedicated user and assign it the **Reporter** role on the target group or project.

2. Generate a `personal_access_token` with `api` scope for that user.

3. Create a random shared secret:

    ```bash
    SHARED_SECRET=$(python -c "import secrets; print(secrets.token_hex(10))")
    ```

4. Clone the repo:

    ```bash
    git clone https://github.com/imtiyaazsalie/mergemate.git
    ```

5. Wire up your config. If you're not setting these as environment variables at runtime:

    - In your configuration: set `config.git_provider = "gitlab"`
    - In your secrets: set your model provider key, then under `[gitlab]` fill in `personal_access_token` (from step 2) and `shared_secret` (from step 3)
    - **Authentication type:** set `auth_type = "oauth_token"` for gitlab.com or modern instances. Use `"private_token"` for older versions (e.g. GitLab 11.x) or private deployments.

6. Build and push the Docker image:

    ```bash
    docker build . -t gitlab_mergemate --target gitlab_webhook -f docker/Dockerfile
    docker push mergemate/mergemate:gitlab_webhook
    ```

7. Provide the environment variables (exact method depends on your container runtime):

    ```bash
    CONFIG__GIT_PROVIDER=gitlab
    GITLAB__PERSONAL_ACCESS_TOKEN=<personal_access_token>
    GITLAB__SHARED_SECRET=<shared_secret>
    GITLAB__URL=https://gitlab.com
    GITLAB__AUTH_TYPE=oauth_token   # or "private_token" for older instances
    OPENAI__KEY=<your_openai_api_key>
    PORT=3000   # optional — override the webhook server port
    ```

8. Create a webhook in your GitLab project. Point the URL at `http[s]://<YOUR_HOST>/webhook`, set the secret token to the value from step 3, and enable **Push events**, **Comments**, and **Merge request events**.

9. Test by opening a merge request or dropping a MergeMate command into a PR comment.

---

## Deploy as a Lambda Function

AWS Lambda env vars can't contain dots — replace each `.` with `__`. For example, `GITLAB.PERSONAL_ACCESS_TOKEN` becomes `GITLAB__PERSONAL_ACCESS_TOKEN`.

1. Follow steps 1–5 from [Run as a Webhook Server](#run-as-a-webhook-server) above.
2. Build a Lambda-compatible image:

    ```shell
    docker buildx build --platform=linux/amd64 . \
      -t mergemate/mergemate:gitlab_lambda \
      --target gitlab_lambda \
      -f docker/Dockerfile.lambda
    ```

3. Push to ECR:

    ```shell
    docker tag mergemate/mergemate:gitlab_lambda \
      <AWS_ACCOUNT>.dkr.ecr.<AWS_REGION>.amazonaws.com/mergemate/mergemate:gitlab_lambda
    docker push <AWS_ACCOUNT>.dkr.ecr.<AWS_REGION>.amazonaws.com/mergemate/mergemate:gitlab_lambda
    ```

4. Create a Lambda function from the image. Set timeout to at least 3 minutes.
5. Give the Lambda a Function URL.
6. Set `AZURE_DEVOPS_CACHE_DIR` to `/tmp` (or another writable path) in the Lambda's environment variables.
7. Use the Function URL as your webhook URL (steps 8–9 of the webhook server setup). It'll be `https://<LAMBDA_FUNCTION_URL>/webhook`.

### Using AWS Secrets Manager

For production Lambda deployments, use Secrets Manager instead of plain environment variables:

1. Create individual secrets for each GitLab webhook. Format:

    ```json
    {
      "gitlab_token": "glpat-xxxxxxxxxxxxxxxxxxxxxxxx",
      "token_name": "project-webhook-001"
    }
    ```

2. Create a main config secret for shared settings:

    ```json
    {
      "openai.key": "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    }
    ```

3. Set these env vars on your Lambda:

    ```bash
    CONFIG__SECRET_PROVIDER=aws_secrets_manager
    AWS_SECRETS_MANAGER__SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:mergemate-main-config-AbCdEf
    ```

4. In your GitLab webhook config, set the **Secret Token** to match the Secrets Manager secret name from step 1 (e.g. `project-webhook-secret-001`).

    !!! important
        When using Secrets Manager, the GitLab webhook secret **must** equal the Secrets Manager secret name.

5. Add `secretsmanager:GetSecretValue` to your Lambda execution role's IAM policy.
