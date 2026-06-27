# How MergeMate Works

MergeMate combines several key capabilities to produce reviews that actually understand your code. Here's what's under the hood:

- [Compression strategy](./compression_strategy.md) — packing large PRs into model context windows without losing signal
- [Dynamic context](./dynamic_context.md) — asymmetric, code-aware context expansion around each change
- [Fetching ticket context](./fetching_ticket_context.md) — pulling issue and Jira details into the review
- [Interactivity](./interactivity.md) — checkbox-driven actions directly in PR comments
- [Local and global metadata](./metadata.md) — multi-stage analysis from hunk-level to org-level
- [Self-reflection](./self_reflection.md) — scoring and re-ranking suggestions before you see them

## From the Blog

Deeper dives into how LLMs perform on real-world coding tasks:

### Code Generation & LLMs

- [Effective AI code suggestions: less is more](https://https://github.com/imtiyaazsalie/mergemate/blob/main/effective-code-suggestions-llms-less-is-more/)
- [State-of-the-art Code Generation with AlphaMergeMate — From Prompt Engineering to Flow Engineering](https://https://github.com/imtiyaazsalie/mergemate/blob/main/mergemateflow-state-of-the-art-code-generation-for-code-contests/)
- [RAG for a Codebase with 10k Repos](https://https://github.com/imtiyaazsalie/mergemate/blob/main/rag-for-large-scale-code-repos/)

### Development Workflows

- [Understanding the Challenges and Pain Points of the Pull Request Cycle](https://https://github.com/imtiyaazsalie/mergemate/blob/main/understanding-the-challenges-and-pain-points-of-the-pull-request-cycle/)
- [Introduction to Code Coverage Testing](https://https://github.com/imtiyaazsalie/mergemate/blob/main/introduction-to-code-coverage-testing/)

### Cost Optimisation

- [Reduce Your Costs by 30% When Using GPT for Python Code](https://https://github.com/imtiyaazsalie/mergemate/blob/main/reduce-your-costs-by-30-when-using-gpt-3-for-python-code/)
