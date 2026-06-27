# Getting started

Once you've [installed MergeMate](../installation/index.md), there are three ways to run it:

1. **CLI** — run commands directly from your terminal
2. **Online** — trigger commands with [PR comments](https://github.com/imtiyaazsalie/mergemate/pull/229#issuecomment-1695021901){:target="_blank"}
3. **Auto-pilot** — let MergeMate fire on every new PR

For the CLI, you can use our [Docker image](../installation/locally.md#using-docker-image) or [run from source](../installation/locally.md#run-from-source).

For online and automatic modes, you'll need to hook up a platform integration: [GitHub App](../installation/github.md#run-as-a-github-app), [GitHub Action](../installation/github.md#run-as-a-github-action), [GitLab webhook](../installation/gitlab.md#run-a-gitlab-webhook-server), or [Bitbucket App](../installation/bitbucket.md#run-using-mergemate-bitbucket-app). Once connected, MergeMate can respond to comments and auto-run on PR events.
