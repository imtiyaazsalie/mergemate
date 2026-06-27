# Metadata Injection & Multi-Stage Analysis

`Supported on: GitHub, GitLab, Bitbucket`

MergeMate builds up a rich picture of each PR through progressive layers of analysis — from individual hunks to organisation-wide preferences — feeding each stage's output into the next.

## Layer 1: Raw PR Data

When a review kicks off, MergeMate pulls:

- PR title and branch name
- Original PR description
- Commit message history
- Diff patches in [hunk format](https://loicpefferkorn.net/2014/02/diff-files-what-are-hunks-and-how-to-extract-them/)
- The full content of every modified file

!!! tip "Organisation-level metadata"
    On top of these inputs, MergeMate can fold in user-supplied preferences like [`extra_instructions` and org best practices](../tools/improve.md#extra-instructions-and-best-practices) to sharpen the analysis.

## Layer 2: AI-Generated Metadata

By default, the first command MergeMate runs is [`describe`](../tools/describe.md). This produces three outputs:

- **PR type** — bug fix, feature, refactor, etc.
- **PR description** — a bullet-point summary of what the PR does
- **Changes walkthrough** — per-file, a one-line summary plus a detailed bullet list of changes

These AI-generated outputs become permanent PR metadata, available to every subsequent command (`review`, `improve`, etc.). This effectively creates a multi-stage chain-of-thought analysis without extra API calls — no added cost or latency.

For example, when generating code suggestions for a file, MergeMate injects the AI-generated file summary right into the prompt:

```diff
## File: 'src/file1.py'
### AI-generated file summary:
- edited function `func1` that does X
- Removed function `func2` that was unused
- ....

@@ ... @@ def func1():
__new hunk__
11  unchanged code line0
12  unchanged code line1
13 +new code line2 added
14  unchanged code line3
__old hunk__
 unchanged code line0
 unchanged code line1
-old code line2 removed
 unchanged code line3

@@ ... @@ def func2():
__new hunk__
...
__old hunk__
...
```

## Layer 3: Extended File Context

The full file contents pulled in Layer 1 are used to expand the context around each change — see [Dynamic Context](./dynamic_context.md) for how that works.

## The Full Stack

These layers span the entire spectrum — from individual hunks, to files, to the full PR, to organisation-wide conventions. Each layer feeds the next, giving the model progressively richer input without redundant API calls. The result: suggestions and feedback that are grounded in the actual shape of your codebase and the intent behind the changes.
