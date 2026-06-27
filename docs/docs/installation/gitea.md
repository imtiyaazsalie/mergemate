# Gitea Integration

## Run as a Webhook Server

1. In Gitea, create a dedicated user with the **Reporter** role on the target group or project.

2. Generate a `personal_access_token` with `api` access for that user.

3. Create a random webhook secret:

    ```bash
    WEBHOOK_SECRET=$(python -c "import secrets; print(secrets.token_hex(10))")
    ```

4. Clone the repo:

    ```bash
    git clone https://github.com/imtiyaazsalie/mergemate.git
    ```

5. Wire up your config. If you're not setting these as environment variables at runtime:

    - Configuration: set `config.git_provider = "gitea"`
    - Secrets: set your model provider key, then under `[gitea]` fill in `personal_access_token` (from step 2) and `webhook_secret` (from step 3)

6. Build and push the Docker image:

    ```bash
    docker build -f docker/Dockerfile -t mergemate:gitea_app --target gitea_app .
    docker push mergemate/mergemate:gitea_webhook
    ```

7. Provide the environment variables (exact method depends on your container runtime):

    ```bash
    CONFIG__GIT_PROVIDER=gitea
    GITEA__PERSONAL_ACCESS_TOKEN=<personal_access_token>
    GITEA__WEBHOOK_SECRET=<webhook_secret>
    GITEA__URL=https://gitea.com   # or your self-hosted URL
    OPENAI__KEY=<your_openai_api_key>
    GITEA__SKIP_SSL_VERIFICATION=false
    GITEA__SSL_CA_CERT=/path/to/cacert.pem
    ```

8. Create a webhook in your Gitea project. Set the URL to `http[s]://<YOUR_HOST>/api/v1/gitea_webhooks`, the secret token to the value from step 3, and enable **Push**, **Comments**, and **Pull request** events.

9. Test by opening a pull request or commenting on one with a MergeMate command.
