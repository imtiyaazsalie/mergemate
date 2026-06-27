# MergeMate

Your pull requests, supercharged with AI.

MergeMate plugs into your workflow — GitHub, GitLab, Bitbucket, Azure DevOps — and handles the grind: reviews, descriptions, code suggestions, changelogs, and more. One tool, every platform.

---

**Start here:**

- [Set it up →](installation/index.md)
- [Run your first command →](usage-guide/index.md)
- [Explore all tools →](tools/index.md)

---

## Ask the docs

Stuck on something? Tag MergeMate in a PR comment:

```
/help "How do I ignore generated files?"
```

The bot replies with a [direct answer](https://github.com/mergemate/mergemate/pull/1241#issuecomment-2365259334) and links to the right docs page.

---

## What it does

| Capability | GitHub | GitLab | Bitbucket | Azure DevOps | Gitea |
|---|---|---|---|---|---|
| **Describe** — summarize the PR | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Review** — catch issues before merge | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Improve** — suggest code changes | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Ask** — query the PR directly | ✅ | ✅ | ✅ | | |
| **Add Docs** — generate documentation | ✅ | ✅ | ✅ | ✅ | |
| **Generate Labels** — auto-label PRs | ✅ | ✅ | ✅ | ✅ | |
| **Update Changelog** — keep history clean | ✅ | ✅ | ✅ | ✅ | |
| **Help** — in-PR assistance | ✅ | ✅ | ✅ | ✅ | |
| **CLI** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **App / Webhook** | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## See it in action

### Describe

![Describe output](https://www.mergemate.ai/images/mergemate/describe_new_short_main.png){width=512}

### Review

![Review output](https://www.mergemate.ai/images/mergemate/review_new_short_main.png){width=512}

### Improve

![Improve output](https://www.mergemate.ai/images/mergemate/improve_new_short_main.png){width=512}

---

## How it works under the hood

MergeMate grabs your PR diff, filters out the noise, and builds a compact, context-rich prompt for the LLM. You get meaningful feedback — fast.

![MergeMate pipeline](https://mergemate.ai/images/mergemate/diagram-v0.9.png)

Curious about the compression? [Read the deep dive →](core-abilities/index.md)
