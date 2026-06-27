# Azure DevOps Integration

## Run in an Azure Pipeline

Add this `azure-pipelines.yml` to your repository:

```yaml
# Disable CI triggers
trigger: none

stages:
- stage: mergemate
  displayName: 'MergeMate'
  jobs:
  - job: mergemate_job
    displayName: 'MergeMate Job'
    pool:
      vmImage: 'ubuntu-latest'
    container:
      image: mergemate/mergemate:latest
      options: --entrypoint ""
    variables:
      - group: mergemate
    steps:
    - script: |
        echo "Running MergeMate"

        # Build the PR URL
        PR_URL="${SYSTEM_COLLECTIONURI}${SYSTEM_TEAMPROJECT}/_git/${BUILD_REPOSITORY_NAME}/pullrequest/${SYSTEM_PULLREQUEST_PULLREQUESTID}"
        echo "PR_URL=$PR_URL"

        # Extract org URL
        ORG_URL=$(echo "$(System.CollectionUri)" | sed 's/\/$//')
        echo "Organization URL: $ORG_URL"

        export azure_devops__org="$ORG_URL"
        export config__git_provider="azure"

        mergemate --pr_url="$PR_URL" describe
        mergemate --pr_url="$PR_URL" review
        mergemate --pr_url="$PR_URL" improve
      env:
        azure_devops__pat: $(azure_devops_pat)
        openai__key: $(OPENAI_KEY)
      displayName: 'Run MergeMate'
```

This fires `describe`, `review`, and `improve` on every merge request. You'll need to export the variables in your Azure DevOps pipeline settings — go to **Pipelines > Library > + Variable group**, create a group called `mergemate`, and add:

- `azure_devops_pat` — your Azure DevOps PAT
- `OPENAI_KEY` — your model provider key


Make sure the pipeline has permission to access the `mergemate` variable group.

!!! note "PR comment triggers"
    Azure Pipelines doesn't support triggering workflows from PR comments. If you find a workable solution, we'd love to see it — drop it in the [issue tracker](https://github.com/imtiyaazsalie/mergemate/issues).

### Build Validation for Azure Repos Git

Azure Repos Git ignores YAML `pr:` triggers. Instead, configure Build Validation on the target branch:

1. Navigate to **Project Settings > Repositories > Branches**.
2. Select the target branch and open **Branch Policies**.
3. Under **Build Validation**, add a policy pointing at the MergeMate pipeline and mark it as Required.
4. You can safely omit the `pr:` section from the YAML.

This only applies to Azure Repos Git. Other providers like GitHub and Bitbucket Cloud use YAML-based PR triggers as expected.

---

## Running from the CLI

Set your git provider in the configuration:

```toml
[config]
git_provider = "azure"
```

Azure DevOps supports two authentication methods:

- **PAT token** — quick to create but has a built-in expiration. Uses your user identity for API calls.
- **DefaultAzureCredential** — leverages managed identity or a service principal through Azure AD. More secure and creates a distinct identity for the agent.

### PAT Authentication

Add this to your secrets file:

```toml
[azure_devops]
org = "https://dev.azure.com/YOUR_ORGANIZATION/"
pat = "YOUR_PAT_TOKEN"
```

### DefaultAzureCredential

Set `AZURE_CLIENT_SECRET` and related env vars directly, or lean on managed identity / `az login` for local dev. The `org` value is always required:

```toml
[azure_devops]
org = "https://dev.azure.com/YOUR_ORGANIZATION/"
# pat is not needed — DefaultAzureCredential handles auth
```

---

## Azure DevOps Webhook

To trigger MergeMate from Azure events, [create a webhook](https://learn.microsoft.com/en-us/azure/devops/service-hooks/services/webhooks?view=azure-devops) manually. Use **Pull request created** to fire a review, or **Pull request commented on** to respond to slash commands (`/<command> <args>`) in PR comments. Note that "Pull request commented on" only supports API v2.0.

Secure the webhook with basic auth — generate a username/password pair and configure them on both the MergeMate server and the Azure DevOps webhook:

```toml
[azure_devops_server]
webhook_username = "<basic auth user>"
webhook_password = "<basic auth password>"
```

!!! warning
    Always serve the webhook endpoint over **HTTPS** to protect the basic auth credentials in transit.
