# Bitbucket Integration

## Run as a Bitbucket Pipeline

1. Drop this into your repo's `bitbucket-pipelines.yml`:

    ```yaml
    pipelines:
      pull-requests:
        '**':
          - step:
              name: MergeMate Review
              image: imtiyaazsalie/mergemate-review:latest
              script:
                - mergemate-review --pr_url=https://bitbucket.org/$BITBUCKET_WORKSPACE/$BITBUCKET_REPO_SLUG/pull-requests/$BITBUCKET_PR_ID review
    ```

2. Under **Repository settings > Pipelines > Repository variables**, add these secured variables:

    - `CONFIG__GIT_PROVIDER` = `bitbucket`
    - `OPENAI__KEY` = `<your key>`
    - `BITBUCKET__AUTH_TYPE` = `bearer` (or `basic`)
    - `BITBUCKET__BEARER_TOKEN` = `<your token>` (required for bearer auth)
    - `BITBUCKET__BASIC_TOKEN` = `<your token>` (required for basic auth)

    Generate a token from **Repository Settings > Security > Access Tokens**. For basic auth, base64-encode your `username:password` pair.

    !!! note
        Bitbucket Pipelines don't support triggering from PR comments.

---

## Bitbucket Server and Data Center

For on-prem deployments, start by generating an HTTP access token from your service account: navigate to **Manage account > HTTP Access tokens > Create Token**.

Add the token to your secrets file:

```toml
[bitbucket_server]
bearer_token = "<your token>"
```

Don't forget to point MergeMate at your instance:

```toml
[bitbucket_server]
url = "https://git.bitbucket.mycompany.com"
```

### CLI Mode

Set the git provider in your config:

```toml
git_provider = "bitbucket_server"
```

Then run:

```shell
mergemate-review --pr_url https://git.bitbucket.mycompany.com/projects/PROJECT/repos/REPO/pull-requests/1 review
```

### Webhook Mode

Build and push the image:

```bash
docker build . -t mergemate/mergemate:bitbucket_server_webhook \
  --target bitbucket_server_webhook \
  -f docker/Dockerfile
docker push mergemate/mergemate:bitbucket_server_webhook
```

Then head to **Projects/Repositories > Settings > Webhooks > Create Webhook**. Fill in the name and URL (ending in `/webhook`, e.g. `https://your-domain.com/webhook`), set authentication to **None**, and tick **Pull Request Opened** as the trigger event.
