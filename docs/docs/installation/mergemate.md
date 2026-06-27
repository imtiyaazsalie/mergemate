# MergeMate Deployment Options

MergeMate runs wherever your code lives. Here's a quick map to help you choose the right setup.

## ⚡ AI-Powered Setup

Let MergeMate figure it out for you:

```bash
pip install mergemate
mergemate init
```

It auto-detects your project and generates `.mergemate.toml` + GitHub Actions workflow using AI. Takes 30 seconds. [See the local guide →](./locally.md)

## 🖥️ Run Locally

Spin it up on your own machine with Docker, pip, or a direct source checkout.

[See the local guide →](./locally.md)

## 🐙 GitHub

Drop a workflow file into your repo and let Actions handle the rest — or run a dedicated GitHub App for tighter control.

[See the GitHub guide →](./github.md)

## 🦊 GitLab

Trigger reviews from your CI pipeline, or stand up a webhook server that listens for merge request events.

[See the GitLab guide →](./gitlab.md)

## 🟦 Bitbucket

Hook into Bitbucket Pipelines for PR-triggered reviews, or deploy a webhook for on-prem Bitbucket Server.

[See the Bitbucket guide →](./bitbucket.md)

## 🔷 Azure DevOps

Add MergeMate to your Azure Pipelines workflow, drive it from the CLI, or configure a webhook endpoint.

[See the Azure DevOps guide →](./azure.md)
