# Similar Issues

**Surfaces related issues from your repository using vector search across issue titles and bodies.**

```
/similar_issue
```

MergeMate indexes all past issues once, then retrieves the closest matches whenever you call the tool — handy for spotting duplicates or finding earlier discussions.

![similar_issue](https://mergemate.ai/images/mergemate/similar_issue.png){width=768}

Trigger it from the CLI:

```
python -m mergemate.cli --issue_url https://github.com/owner/repo/issues/42 similar_issue
```

## Vector database options

Choose your backend in the config:

| Database | Best for |
|---|---|
| **LanceDB** (default) | Zero-config, embedded — works out of the box. |
| **Pinecone** | Managed, scales well for large repos. |
| **Qdrant** | Self-hosted or cloud, open-source. |

### Pinecone

```toml
# .secrets.toml
[pinecone]
api_key = "..."
environment = "..."

# configuration.toml
[pr_similar_issue]
vectordb = "pinecone"
```

### Qdrant

```toml
# .secrets.toml
[qdrant]
url = "https://your-instance.qdrant.io"
api_key = "..."

# configuration.toml
[pr_similar_issue]
vectordb = "qdrant"
```

Get a free Qdrant instance at [cloud.qdrant.io](https://cloud.qdrant.io/).

## Automation

Add `/similar_issue` to the `pr_commands` list to run it automatically when a new issue is opened.

## Tips

- **Index happens once.** The first call builds the vector index from all existing issues. Subsequent calls are fast.
- **Use it for triage.** If a similar issue is already in progress, link them and save duplicate work.
- **Qdrant or Pinecone** make sense for repos with thousands of issues; for smaller repos, LanceDB is the simplest path.
