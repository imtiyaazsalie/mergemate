# Self-Reflection

`Supported on: GitHub, GitLab, Bitbucket`

MergeMate doesn't just generate suggestions — it scores them, re-ranks them, and filters out the ones that don't hold up. This self-reflection loop means you see fewer irrelevant suggestions and spend less time triaging.

## Why Hierarchical Presentation Matters

Not every suggestion an AI generates is worth your attention. The key is making it fast to spot the good ones and dismiss the noise.

MergeMate presents suggestions in a layered structure designed for rapid scanning:

- Suggestions are grouped by **category**, so you can dismiss entire classes of suggestions at once.
- Each suggestion starts as a **one-line summary**. Click to expand into a full description.
- Expanded view gives you a **comprehensive explanation** and a **code snippet** showing the proposed change.

Developers typically spend 5–10 seconds per suggestion with this format — enough time to assess relevance without breaking flow.

## How Self-Reflection Works

The model's first pass generates suggestions and attempts to rank them by importance. In practice, models often struggle to do both well simultaneously — and the initial set sometimes contains obvious errors.

The self-reflection step fixes this:

1. All generated suggestions are fed back to the model in a follow-up call.
2. The model scores each suggestion on a scale of 0–10, with a rationale.
3. Scores are used to re-rank the suggestions. Suggestions scoring zero are discarded.
4. Optionally, everything below a configurable threshold is filtered out.

Presenting all suggestions together gives the model a full view, helping it make more consistent decisions than evaluating each one in isolation.

The outcome: suggestions are reliably ordered by importance, clearly wrong ones are eliminated, and you can set a minimum quality bar that fits your team's standards.

## Example

![Self-reflection scoring](https://mergemate.ai/images/mergemate/self_reflection1.png){width=768}
![Self-reflection re-ranking](https://mergemate.ai/images/mergemate/self_reflection2.png){width=768}

## Configuration

```toml
[pr_code_suggestions]
suggestions_score_threshold = 0   # Drop suggestions below this score (0–10)
```

Set this higher to enforce a stricter quality bar — only suggestions that clear the threshold make it to your PR.
