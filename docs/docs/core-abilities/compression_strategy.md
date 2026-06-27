# Compression Strategy

`Supported on: GitHub, GitLab, Bitbucket`

## The Two Scenarios

Every PR falls into one of two buckets:

1. Small enough to fit in a single model prompt (system prompt + code)
2. Too large for a single prompt, requiring smart trimming

Both start with the same triage step.

### Language Prioritisation

Before compression even kicks in, MergeMate sorts your repo's files by relevance:

1. Binary files and non-code assets (images, PDFs, etc.) are discarded immediately.
2. The repo's primary languages are identified.
3. PR files are grouped and sorted by language prevalence, descending:

    ```
    [[file.py, file2.py], [file3.js, file4.jsx], [readme.md]]
    ```

### Small PRs

When everything fits, MergeMate simply expands each patch's surrounding context by three lines above and below — no trimming needed.

### Large PRs

#### Why Compression Matters

Some PRs are enormous, packed with changes that vary wildly in relevance. The goal is to squeeze as much signal as possible into a single prompt while ruthlessly cutting noise.

#### The Strategy

MergeMate favours additions over deletions:

- All deleted files are collapsed into a single list.
- Within each file patch, hunks that only contain deletions are stripped out — they add noise without contributing to the review of what's new.

#### Adaptive Token-Aware Fitting

Using [tiktoken](https://github.com/openai/tiktoken), MergeMate tokenizes the remaining patches and fits them into the prompt with a greedy algorithm:

1. Within each language group, files are sorted by token count (largest first):

    ```
    [[file2.py, file.py], [file4.jsx, file3.js], [readme.md]]
    ```

2. MergeMate walks through patches in priority order.
3. Each patch is added until the prompt hits a buffer below the max token limit.
4. Any remaining patches get listed as `other modified files` — added until the hard token cap is reached, then the rest are skipped.
5. If there's still room, the `deleted files` list is appended until the cap, with the remainder dropped.

#### Visual Summary

![Compression flow](https://mergemate.ai/images/git_patch_logic.png){width=768}
